const LOCAL_API = "http://127.0.0.1:8765";
let session = { running: false, tabId: null, discovered: 0, added: 0, batches: 0, message: "等待开始" };
const pendingLikes = new Map();
let finishPromise = null;

const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function saveState(patch = {}) {
  session = { ...session, ...patch };
  await chrome.storage.local.set({ archiveState: session });
}

async function debugCommand(method, params = {}) {
  return chrome.debugger.sendCommand({ tabId: session.tabId }, method, params);
}

async function sendPayload(payload) {
  const response = await fetch(`${LOCAL_API}/api/ingest/x-response`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  if (result.stop_requested && session.running) {
    await finish(`已连续读取 ${result.existing_streak} 条本地已有推文，正在下载媒体`);
  }
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
      const text = result.base64Encoded ? atob(result.body) : result.body;
      await sendPayload(JSON.parse(text));
    } catch (error) {
      await saveState({ message: `读取已完成的 Likes 响应失败：${error.message}` });
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
          if (globalThis.__localFavoritesArchiveTimer) clearInterval(globalThis.__localFavoritesArchiveTimer);
          globalThis.__localFavoritesArchiveTimer = null;
        }
      });
    } catch (_) {}
    try { await chrome.debugger.detach({ tabId }); } catch (_) {}
  }
  try { await fetch(`${LOCAL_API}/api/ingest/finish`, { method: "POST" }); } catch (_) {}
}

async function finish(message) {
  if (!finishPromise) {
    finishPromise = finishOnce(message).finally(() => { finishPromise = null; });
  }
  return finishPromise;
}

async function installScrollDriver(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      if (globalThis.__localFavoritesArchiveTimer) clearInterval(globalThis.__localFavoritesArchiveTimer);
      let unchanged = 0;
      let previousHeight = document.body.scrollHeight;
      globalThis.__localFavoritesArchiveTimer = setInterval(() => {
        window.scrollBy({ top: Math.max(window.innerHeight * 0.85, 600), behavior: "smooth" });
        const height = document.body.scrollHeight;
        const bottom = window.scrollY + window.innerHeight >= height - 20;
        unchanged = bottom && height === previousHeight ? unchanged + 1 : 0;
        previousHeight = height;
        if (unchanged >= 6) {
          clearInterval(globalThis.__localFavoritesArchiveTimer);
          globalThis.__localFavoritesArchiveTimer = null;
          chrome.runtime.sendMessage({ type: "auto-finished" });
        }
      }, 1800);
    }
  });
}

async function start(tabId, url) {
  if (session.running) throw new Error("同步已经在运行");
  await fetch(`${LOCAL_API}/api/sync/status`).then(response => {
    if (!response.ok) throw new Error("本地归档服务未运行");
  }).catch(() => { throw new Error("无法连接 http://127.0.0.1:8765"); });
  await fetch(`${LOCAL_API}/api/ingest/start`, { method: "POST" });
  if (!/^https:\/\/(x|twitter)\.com\//i.test(url || "")) {
    throw new Error("请先在当前标签页打开 X");
  }
  let targetUrl = url;
  const isLikes = /^https:\/\/(x|twitter)\.com\/(?:[^/]+|i)\/likes(?:[/?#]|$)/i.test(url);
  if (!isLikes) {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const reserved = new Set(["home", "explore", "notifications", "messages", "search", "settings", "login", "signup", "compose", "tos", "privacy", "i"]);
        const paths = [...document.querySelectorAll('a[href^="/"]')].map(link => link.getAttribute("href").split("?")[0].replace(/\/$/, ""));
        const profile = paths.find(path => {
          const parts = path.split("/").filter(Boolean);
          return parts.length === 1 && !reserved.has(parts[0].toLowerCase());
        });
        return profile ? `${location.origin}${profile}/likes` : null;
      }
    });
    if (!result.result) throw new Error("无法从当前页面确定账号，请手动打开个人主页的 Likes 标签后重试");
    targetUrl = result.result;
  }
  finishPromise = null;
  await chrome.debugger.attach({ tabId }, "1.3");
  await saveState({ running: true, tabId, discovered: 0, added: 0, batches: 0, message: "正在重新加载 Likes 页面" });
  await debugCommand("Network.enable");
  if (targetUrl === url) await chrome.tabs.reload(tabId);
  else await chrome.tabs.update(tabId, { url: targetUrl });
  await delay(2500);
  await installScrollDriver(tabId);
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message.type === "start") {
      await start(message.tabId, message.url);
      return { ok: true };
    }
    if (message.type === "stop") {
      await finish("已手动停止，正在下载媒体");
      return { ok: true };
    }
    if (message.type === "auto-finished") {
      await finish("已到达当前可访问内容末尾，正在下载媒体");
      return { ok: true };
    }
    if (message.type === "status") return { ok: true, state: session };
    return { ok: false, error: "未知操作" };
  })().then(sendResponse).catch(error => sendResponse({ ok: false, error: error.message }));
  return true;
});
