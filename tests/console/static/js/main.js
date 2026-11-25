import { ActionQueue } from "./ActionQueue.js";
import { setupUI } from "./ui.js";

async function runAction(fn, params) {
  const res = await fetch("/api/action/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ function: fn, params: params || {} }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || res.statusText || "action failed";
    console.error("action failed", fn, detail);
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function setupCamera() {
  const img = document.getElementById("camera");
  const overlay = document.getElementById("camera-overlay");

  const showError = (msg) => {
    overlay.textContent = msg;
    overlay.classList.remove("hidden");
  };

  const reload = () => {
    img.src = `/api/camera/stream?t=${Date.now()}`;
  };

  img.onload = () => overlay.classList.add("hidden");
  img.onerror = () => {
    showError("摄像头未连接 · 将自动重试");
    setTimeout(reload, 3000);
  };
  reload();
  return { reload };
}

async function main() {
  const [actionsRes, robotRes] = await Promise.all([
    fetch("/api/actions"),
    fetch("/api/robot"),
  ]);
  const actionsJson = await actionsRes.json();
  const robot = await robotRes.json();
  const actions = actionsJson.actions || [];

  const queue = new ActionQueue({
    play: async (fn, params) => {
      await runAction(fn, params);
    },
  });

  const camera = setupCamera();
  setupUI({
    actions,
    robot,
    queue,
    onConnected: () => camera.reload(),
  });
}

main().catch((err) => {
  console.error(err);
  const overlay = document.getElementById("camera-overlay");
  if (overlay) {
    overlay.textContent = `启动失败: ${err.message || err}`;
    overlay.classList.remove("hidden");
  }
});
