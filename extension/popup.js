const status = document.getElementById("status");

async function refresh() {
  const response = await chrome.runtime.sendMessage({ type: "status" });
  const state = response.state || {};
  status.textContent = state.message || "等待开始";
  document.getElementById("start").disabled = Boolean(state.running);
  document.getElementById("restart").disabled = Boolean(state.running);
  document.getElementById("stop").disabled = !state.running;
}

async function start(mode) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const response = await chrome.runtime.sendMessage({ type: "start", mode, tabId: tab.id, url: tab.url });
  if (!response.ok) status.textContent = response.error;
  await refresh();
}

document.getElementById("start").onclick = () => start("resume");
document.getElementById("restart").onclick = () => start("restart");

document.getElementById("stop").onclick = async () => {
  const response = await chrome.runtime.sendMessage({ type: "stop" });
  if (!response.ok) status.textContent = response.error;
  await refresh();
};

refresh();
setInterval(refresh, 1000);
