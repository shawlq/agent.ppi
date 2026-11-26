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

  img.onload = () => {
    fetch("/api/robot")
      .then((r) => r.json())
      .then((robot) => {
        if (robot.agent === "ppi_agent" && robot.mode !== "mock") {
          overlay.classList.add("hidden");
        } else if (robot.agent === "sim_agent") {
          // MJPEG from sim head camera — hide overlay when bytes actually arrived.
          overlay.classList.add("hidden");
        } else if (!robot.agent) {
          showError("请先加载 Agent");
        } else {
          showError("mock / 无摄像头流");
        }
      })
      .catch(() => overlay.classList.add("hidden"));
  };
  img.onerror = () => {
    fetch("/api/robot")
      .then((r) => r.json())
      .then((robot) => {
        if (robot.agent === "sim_agent") {
          showError("请打开仿真页以生成摄像头画面");
        } else {
          showError("摄像头未连接 · 将自动重试");
        }
      })
      .catch(() => showError("摄像头未连接 · 将自动重试"));
    setTimeout(reload, 3000);
  };
  reload();
  return { reload };
}

async function main() {
  const camera = setupCamera();

  const queue = new ActionQueue({
    play: async (fn, params) => runAction(fn, params),
  });

  setupUI({
    queue,
    onAgentLoaded: () => camera.reload(),
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
