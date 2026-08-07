const status = document.getElementById("status");
const scrollSpeed = document.getElementById("scroll-speed");
const scrollSpeedValue = document.getElementById("scroll-speed-value");

function renderScrollSpeed(value) {
  scrollSpeed.value = String(value);
  scrollSpeedValue.textContent = `${(Number(value) / 1000).toFixed(1)} 秒`;
}

async function refresh() {
  const response = await chrome.runtime.sendMessage({ type: "status" });
  const state = response.state || {};
  status.textContent = state.message || "等待开始";
  document.getElementById("start").disabled = Boolean(state.running);
  document.getElementById("stop").disabled = !state.running;
  renderScrollSpeed(state.scrollIntervalMs || 1800);
}

scrollSpeed.addEventListener("input", async () => {
  renderScrollSpeed(scrollSpeed.value);
  await chrome.runtime.sendMessage({ type: "set-scroll-speed", value: Number(scrollSpeed.value) });
});

async function start() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const response = await chrome.runtime.sendMessage({ type: "start", tabId: tab.id, url: tab.url });
  if (!response.ok) status.textContent = response.error;
  await refresh();
}

document.getElementById("start").onclick = () => start();

document.getElementById("stop").onclick = async () => {
  const response = await chrome.runtime.sendMessage({ type: "stop" });
  if (!response.ok) status.textContent = response.error;
  await refresh();
};

refresh();
setInterval(refresh, 1000);
