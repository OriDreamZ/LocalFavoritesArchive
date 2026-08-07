const LOCAL_API = "http://127.0.0.1:8765";
let session = { running: false, tabId: null, discovered: 0, added: 0, batches: 0, message: "等待开始" };
const pendingLikes = new Map();
let scrollIntervalMs = 1800;

async function setScrollSpeed(value) {
  scrollIntervalMs = Math.min(5000, Math.max(500, Math.round(Number(value) / 100) * 100));
  await chrome.storage.local.set({ scrollIntervalMs });
  await saveState({ scrollIntervalMs });
  if (session.running && session.tabId !== null) await installScrollDriver(session.tabId, scrollIntervalMs);
  return scrollIntervalMs;
}

chrome.storage.local.get({ scrollIntervalMs: 1800 }).then(({ scrollIntervalMs: value }) => setScrollSpeed(value));
let finishPromise = null;

async function saveState(patch = {}) {
  session = { ...session, ...patch };
  await chrome.storage.local.set({ archiveState: session });
}

async function sendPayload(payload) {
  const response = await fetch(`${LOCAL_API}/api/ingest/x-response`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Local-Favorites-Client": "extension" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error(`本地服务返回 ${response.status}`);
  const result = await response.json();
  await saveState({
    discovered: session.discovered + result.discovered,
    added: session.added + result.new,
    batches: session.batches + 1,
    message: `已发现 ${session.discovered + result.discovered} 条，新增 ${session.added + result.new} 条`
  });
  if (result.stop_requested && session.running) await finish(`已连续读取 ${result.existing_streak} 条本地已有推文，正在完成下载`);
}

chrome.debugger.onEvent.addListener(async (source, method, params) => {
  if (!session.running || source.tabId !== session.tabId) return;
  if (method === "Network.responseReceived") {
    const url = params.response?.url || "";
    if (url.includes("/graphql/") && /Likes/i.test(url) && params.response.status >= 200 && params.response.status < 300) {
      pendingLikes.set(params.requestId, url);
    }
    return;
  }
  if (method === "Network.loadingFailed") {
    pendingLikes.delete(params.requestId);
    return;
  }
  if (method === "Network.loadingFinished" && pendingLikes.has(params.requestId)) {
    pendingLikes.delete(params.requestId);
    try {
      const result = await chrome.debugger.sendCommand(source, "Network.getResponseBody", { requestId: params.requestId });
      const body = result.base64Encoded ? atob(result.body) : result.body;
      await sendPayload(JSON.parse(body));
    } catch (error) {
      await saveState({ message: `读取 Likes 响应失败：${error.message}` });
    }
  }
});

chrome.debugger.onDetach.addListener(source => {
  if (source.tabId === session.tabId && session.running) saveState({ running: false, message: "Chrome 已停止调试当前标签页" });
});

async function finishOnce(message) {
  const tabId = session.tabId;
  pendingLikes.clear();
  await saveState({ running: false, tabId: null, message });
  if (tabId !== null) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        func: () => {
          if (globalThis.__localFavoritesArchiveScrollTimer) clearInterval(globalThis.__localFavoritesArchiveScrollTimer);
          globalThis.__localFavoritesArchiveScrollTimer = null;
        }
      });
    } catch (_) {}
    try { await chrome.debugger.detach({ tabId }); } catch (_) {}
  }
  try { await fetch(`${LOCAL_API}/api/ingest/finish`, { method: "POST", headers: { "X-Local-Favorites-Client": "extension" } }); } catch (_) {}
}

async function finish(message) {
  if (!finishPromise) finishPromise = finishOnce(message).finally(() => { finishPromise = null; });
  return finishPromise;
}

async function installScrollDriver(tabId, intervalMs) {
  let lastError;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        func: (delayMs) => {
          if (globalThis.__localFavoritesArchiveScrollTimer) clearInterval(globalThis.__localFavoritesArchiveScrollTimer);
          let unchanged = 0;
          let previousHeight = document.documentElement.scrollHeight;
          globalThis.__localFavoritesArchiveScrollTimer = setInterval(() => {
            const amount = Math.max(window.innerHeight * 0.85, 600);
            window.scrollBy({ top: amount, behavior: "smooth" });
            const root = document.scrollingElement || document.documentElement;
            root.scrollTop += amount;
            const height = document.documentElement.scrollHeight;
            const bottom = window.scrollY + window.innerHeight >= height - 20 || root.scrollTop + root.clientHeight >= root.scrollHeight - 20;
            unchanged = bottom && height === previousHeight ? unchanged + 1 : 0;
            previousHeight = height;
            if (unchanged >= 6) {
              clearInterval(globalThis.__localFavoritesArchiveScrollTimer);
              globalThis.__localFavoritesArchiveScrollTimer = null;
              chrome.runtime.sendMessage({ type: "auto-finished" });
            }
          }, delayMs);
        },
        args: [intervalMs]
      });
      return;
    } catch (error) {
      lastError = error;
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
  throw lastError || new Error("无法注入自动翻页脚本");
}

async function waitForTabReady(tabId) {
  const tab = await chrome.tabs.get(tabId);
  if (tab.status === "complete") return;
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { chrome.tabs.onUpdated.removeListener(listener); reject(new Error("Likes 页面加载超时")); }, 15000);
    const listener = (updatedTabId, changeInfo) => {
      if (updatedTabId !== tabId || changeInfo.status !== "complete") return;
      clearTimeout(timeout);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    };
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function start(tabId, url) {
  if (session.running) throw new Error("同步已经在运行");
  const health = await fetch(`${LOCAL_API}/api/sync/status`).catch(() => null);
  if (!health?.ok) throw new Error("无法连接 http://127.0.0.1:8765");
  if (!/^https:\/\/(x|twitter)\.com\//i.test(url || "")) throw new Error("请先在当前标签页打开 X");
  let targetUrl = url;
  const isLikes = /^https:\/\/(x|twitter)\.com\/(?:[^/]+|i)\/likes(?:[/?#]|$)/i.test(url);
  if (!isLikes) {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const reserved = new Set(["home", "explore", "notifications", "messages", "search", "settings", "login", "signup", "compose", "tos", "privacy", "i"]);
        const paths = [...document.querySelectorAll('a[href^="/"]')].map(link => link.getAttribute("href").split("?")[0].replace(/\/$/, ""));
        const profile = paths.find(path => { const parts = path.split("/").filter(Boolean); return parts.length === 1 && !reserved.has(parts[0].toLowerCase()); });
        return profile ? `${location.origin}${profile}/likes` : null;
      }
    });
    if (!result.result) throw new Error("无法确定账号，请手动打开账号 Likes 页面后重试");
    targetUrl = result.result;
  }
  await fetch(`${LOCAL_API}/api/ingest/start`, { method: "POST", headers: { "X-Local-Favorites-Client": "extension" } });
  finishPromise = null;
  await chrome.debugger.attach({ tabId }, "1.3");
  await saveState({ running: true, tabId, discovered: 0, added: 0, batches: 0, message: "正在刷新 Likes 页面并监听网络响应" });
  await chrome.debugger.sendCommand({ tabId }, "Network.enable");
  if (targetUrl === url) await chrome.tabs.reload(tabId);
  else await chrome.tabs.update(tabId, { url: targetUrl });
  await waitForTabReady(tabId);
  await new Promise(resolve => setTimeout(resolve, 1000));
  await installScrollDriver(tabId, scrollIntervalMs);
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message.type === "start") { await start(message.tabId, message.url); return { ok: true }; }
    if (message.type === "stop") { await finish("已手动停止，正在完成下载"); return { ok: true }; }
    if (message.type === "auto-finished") { await finish("已到达 Likes 页面末尾，正在完成下载"); return { ok: true }; }
    if (message.type === "set-scroll-speed") return { ok: true, scrollIntervalMs: await setScrollSpeed(message.value) };
    if (message.type === "status") return { ok: true, state: { ...session, scrollIntervalMs } };
    return { ok: false, error: "未知操作" };
  })().then(sendResponse).catch(error => sendResponse({ ok: false, error: error.message }));
  return true;
});
