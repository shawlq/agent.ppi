/**
 * Right panel: connect, sim-style action list (resizable), queue.
 */
export function setupUI({ actions, robot, queue, onConnected }) {
  const actionsList = document.getElementById("actions-list");
  const actionsToggle = document.getElementById("actions-toggle");
  const actionsBody = document.getElementById("actions-body");
  const actionsResize = document.getElementById("actions-resize");
  const queueList = document.getElementById("queue-list");
  const queueEmpty = document.getElementById("queue-empty");
  const queueClear = document.getElementById("queue-clear");
  const robotMeta = document.getElementById("robot-meta");
  const healthDot = document.getElementById("health-dot");
  const healthText = document.getElementById("health-text");
  const hostInput = document.getElementById("robot-host");
  const connectBtn = document.getElementById("connect-btn");

  const HEIGHT_KEY = "console.actionsListHeight";
  const MIN_H = 120;
  const MAX_H = Math.max(200, window.innerHeight - 220);

  hostInput.value = robot.robot_host || "";

  // Restore / apply resizable instruction list height.
  const savedH = Number(localStorage.getItem(HEIGHT_KEY));
  const initH = Number.isFinite(savedH) && savedH >= MIN_H ? savedH : 280;
  actionsList.style.height = `${Math.min(initH, MAX_H)}px`;
  actionsList.style.maxHeight = "none";

  actionsToggle.addEventListener("click", () => {
    const open = actionsToggle.getAttribute("aria-expanded") === "true";
    actionsToggle.setAttribute("aria-expanded", open ? "false" : "true");
    actionsBody.classList.toggle("collapsed", open);
  });

  // Drag handle to resize instruction list.
  if (actionsResize) {
    let dragging = false;
    let startY = 0;
    let startH = 0;

    const onMove = (ev) => {
      if (!dragging) return;
      const dy = ev.clientY - startY;
      const next = Math.min(MAX_H, Math.max(MIN_H, startH + dy));
      actionsList.style.height = `${next}px`;
    };
    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      document.body.classList.remove("resizing");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      const h = parseFloat(actionsList.style.height);
      if (Number.isFinite(h)) localStorage.setItem(HEIGHT_KEY, String(Math.round(h)));
    };

    actionsResize.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      dragging = true;
      startY = ev.clientY;
      startH = actionsList.getBoundingClientRect().height;
      document.body.classList.add("resizing");
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    });
  }

  actionsList.innerHTML = "";
  for (const action of actions) {
    const row = document.createElement("div");
    row.className = "action-row";

    const name = document.createElement("div");
    name.className = "action-name";
    name.textContent = action.action;
    name.title = `${action.function} · ${action.cost_time_sec}s`;

    const paramInput = document.createElement("input");
    paramInput.type = "number";
    const hasParam = Array.isArray(action.params) && action.params.length > 0;
    if (hasParam) {
      const p = action.params[0];
      paramInput.placeholder = p.label || p.name;
      paramInput.value = p.default ?? 90;
      paramInput.title = p.label || p.name;
    } else {
      paramInput.disabled = true;
      paramInput.placeholder = "—";
      paramInput.title = "无参数";
    }

    const timesInput = document.createElement("input");
    timesInput.type = "number";
    timesInput.min = "1";
    timesInput.step = "1";
    timesInput.value = "1";
    timesInput.title = "执行次数";

    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "btn-add";
    addBtn.textContent = "+";
    addBtn.title = "加入队列";

    const enqueue = () => {
      const params = {};
      if (hasParam) {
        const p = action.params[0];
        const raw = Number(paramInput.value);
        params[p.name] = Number.isFinite(raw) ? raw : p.default ?? 90;
      }
      const times = Number(timesInput.value);
      queue.enqueue(action, params, times);
    };

    addBtn.addEventListener("click", enqueue);
    name.addEventListener("dblclick", enqueue);

    row.append(name, paramInput, timesInput, addBtn);
    actionsList.appendChild(row);
  }

  queueClear.addEventListener("click", () => queue.clear());

  queue.onChange = (snapshot) => {
    queueList.innerHTML = "";
    if (!snapshot.length) {
      queueEmpty.classList.remove("hidden");
      return;
    }
    queueEmpty.classList.add("hidden");
    for (const item of snapshot) {
      const li = document.createElement("li");
      li.className = "queue-item" + (item.status === "running" ? " running" : "");
      const left = document.createElement("span");
      left.textContent =
        item.status === "running" ? `▶ ${item.label}` : item.label;
      const meta = document.createElement("span");
      meta.className = "meta";
      const paramText =
        item.params && item.params.angle_deg != null
          ? `${item.params.angle_deg}° · `
          : "";
      meta.textContent = `${paramText}${item.remaining}/${item.times} · ${item.cost}s`;
      li.append(left, meta);
      queueList.appendChild(li);
    }
  };
  queue.onChange(queue.snapshot);

  robotMeta.textContent = `host ${robot.robot_host || "?"} · mode ${robot.mode || "?"}`;

  async function refreshHealth() {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      const rosOk = !!(data.ros && data.ros.ok);
      const videoOk = !!(data.video && data.video.ok);
      healthDot.className = "dot";
      if (data.mode === "mock") {
        healthDot.classList.add("warn");
        healthText.textContent = "mock · 队列可演示，无真机";
      } else if (rosOk && videoOk) {
        healthDot.classList.add("ok");
        healthText.textContent = "rosbridge + 视频正常";
      } else if (rosOk || videoOk) {
        healthDot.classList.add("warn");
        healthText.textContent = `部分可用 · ros ${rosOk ? "ok" : "no"} · cam ${videoOk ? "ok" : "no"}`;
      } else {
        healthDot.classList.add("err");
        healthText.textContent = "未连接 · 检查机器人与前置节点";
      }
      const host = data.robot_host || robot.robot_host;
      robotMeta.textContent = `host ${host} · mode ${data.mode}`;
      if (document.activeElement !== hostInput && host) {
        hostInput.value = host;
      }
    } catch {
      healthDot.className = "dot err";
      healthText.textContent = "health 请求失败";
    }
  }

  async function connectRobot() {
    const host = hostInput.value.trim();
    if (!host) {
      healthDot.className = "dot err";
      healthText.textContent = "请输入 IP 地址";
      return;
    }
    connectBtn.disabled = true;
    healthText.textContent = `连接 ${host}…`;
    try {
      const res = await fetch("/api/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ host }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = data.detail || res.statusText;
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }
      robot.robot_host = host;
      if (typeof onConnected === "function") onConnected(host);
      await refreshHealth();
    } catch (err) {
      healthDot.className = "dot err";
      healthText.textContent = `连接失败: ${err.message || err}`;
    } finally {
      connectBtn.disabled = false;
    }
  }

  connectBtn.addEventListener("click", connectRobot);
  hostInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      connectRobot();
    }
  });

  refreshHealth();
  setInterval(refreshHealth, 5000);
}
