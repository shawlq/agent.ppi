/**
 * Right panel: agent load, resizable action list, queue.
 */
import { showToast, formatDetail } from "./toast.js";

export function setupUI({ queue, onAgentLoaded }) {
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
  const agentSelect = document.getElementById("agent-select");
  const agentLoadBtn = document.getElementById("agent-load-btn");
  const actionStatus = document.getElementById("action-status");
  const hintBar = document.getElementById("hint-bar");

  /** @type {object[]} */
  let actions = [];
  /** @type {object} */
  let robot = { mode: "?", robot_host: "" };

  const HEIGHT_KEY = "console.actionsListHeight";
  const MIN_H = 120;
  const MAX_H = Math.max(200, window.innerHeight - 220);

  const savedH = Number(localStorage.getItem(HEIGHT_KEY));
  const initH = Number.isFinite(savedH) && savedH >= MIN_H ? savedH : 280;
  actionsList.style.height = `${Math.min(initH, MAX_H)}px`;
  actionsList.style.maxHeight = "none";

  function setStatus(msg, kind) {
    if (!actionStatus) return;
    actionStatus.textContent = msg || "";
    actionStatus.classList.remove("ok", "err");
    if (kind) actionStatus.classList.add(kind);
  }

  function visibleParam(action) {
    const params = Array.isArray(action?.params) ? action.params : [];
    return params.find((p) => p.name === "angle_deg") || params[0] || null;
  }

  function fillActions(list) {
    actions = list || [];
    actionsList.innerHTML = "";
    if (!actions.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.style.padding = "10px";
      empty.textContent = "无动作（请先加载 Agent）";
      actionsList.appendChild(empty);
      return;
    }

    for (const action of actions) {
      const row = document.createElement("div");
      row.className = "action-row";

      const name = document.createElement("div");
      name.className = "action-name";
      name.textContent = action.action;
      name.title = `${action.function} · ${action.cost_time_sec}s`;

      const paramInput = document.createElement("input");
      paramInput.type = "number";
      const p = visibleParam(action);
      const hasParam = !!p;
      if (hasParam) {
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
          const raw = Number(paramInput.value);
          params[p.name] = Number.isFinite(raw) ? raw : p.default ?? 90;
        }
        const times = Number(timesInput.value);
        queue.enqueue(action, params, times);
        setStatus(`已入队: ${action.action}`, "ok");
      };

      addBtn.addEventListener("click", enqueue);
      name.addEventListener("dblclick", enqueue);

      row.append(name, paramInput, timesInput, addBtn);
      actionsList.appendChild(row);
    }
  }

  actionsToggle.addEventListener("click", () => {
    const open = actionsToggle.getAttribute("aria-expanded") === "true";
    actionsToggle.setAttribute("aria-expanded", open ? "false" : "true");
    actionsBody.classList.toggle("collapsed", open);
  });

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

  queue.onError = (err, item) => {
    const msg = `${item?.label || ""} ${err.message || err}`.trim();
    setStatus(`执行失败: ${msg}`, "err");
    showToast(msg, { title: "动作执行失败", kind: "err" });
  };
  queue.onSuccess = (item, result) => {
    const ok = result && result.ok !== false;
    setStatus(
      ok ? `完成: ${item.label}` : `失败: ${item.label}`,
      ok ? "ok" : "err"
    );
  };

  async function refreshAgents() {
    try {
      const res = await fetch("/api/agents");
      const data = await res.json();
      const list = data.agents || [];
      const prev = agentSelect.value;
      agentSelect.innerHTML = "";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = list.length ? "选择 *_agent…" : "未发现 agent";
      agentSelect.appendChild(placeholder);
      for (const a of list) {
        const opt = document.createElement("option");
        opt.value = a.name;
        opt.textContent = a.name;
        agentSelect.appendChild(opt);
      }
      if (prev && list.some((a) => a.name === prev)) {
        agentSelect.value = prev;
      } else if (list.some((a) => a.name === "sim_agent")) {
        agentSelect.value = "sim_agent";
      }
    } catch (err) {
      showToast(String(err.message || err), { title: "列举 Agent 失败", kind: "err" });
    }
  }

  async function loadSelectedAgent() {
    const name = agentSelect.value;
    if (!name) {
      showToast("请先在右上角选择 *_agent", { title: "未选择 Agent", kind: "err" });
      return;
    }
    agentLoadBtn.disabled = true;
    healthText.textContent = `加载 ${name}…`;
    setStatus(`加载 ${name}…`);
    try {
      const res = await fetch("/api/agents/load", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = formatDetail(data.detail || data.message || res.statusText);
        const title = data.error_kind || "加载 Agent 失败";
        throw Object.assign(new Error(detail), { title, raw: data });
      }

      // Connect failure after partial load: backend may return ok:false with connect_error.
      if (data.ok === false || data.connect_error) {
        const detail = formatDetail(
          data.connect_error || data.detail || "连接失败（proxy.ip）"
        );
        showToast(detail, {
          title: data.error_kind || "Agent 连接失败",
          kind: "err",
          durationMs: 12000,
        });
      }

      robot = data.robot || {};
      const host = robot.robot_host || robot.ip || "";
      fillActions((await (await fetch("/api/actions")).json()).actions || []);
      robotMeta.textContent = `agent ${name} · ip ${host || "?"} · mode ${data.mode || "?"}`;
      if (hintBar) {
        hintBar.textContent =
          name === "sim_agent"
            ? "sim_agent · /sim_dog/command → 本地仿真"
            : "ppi_agent · runActionGroup / velocity";
      }
      if (!data.connect_error) {
        setStatus(`已加载 ${name}（${data.actions || 0} 个动作）· ip ${host}`, "ok");
      } else {
        setStatus(`已加载 ${name}，但连接失败`, "err");
      }
      if (typeof onAgentLoaded === "function") onAgentLoaded(data);
      await refreshHealth();
    } catch (err) {
      healthDot.className = "dot err";
      healthText.textContent = `加载失败`;
      const msg = err.message || String(err);
      setStatus(`加载失败: ${msg}`, "err");
      showToast(msg, {
        title: err.title || "加载 Agent 失败",
        kind: "err",
        durationMs: 12000,
      });
    } finally {
      agentLoadBtn.disabled = false;
    }
  }

  agentLoadBtn.addEventListener("click", loadSelectedAgent);

  async function refreshHealth() {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      const rosOk = !!(data.ros && data.ros.ok);
      const videoOk = !!(data.video && data.video.ok);
      healthDot.className = "dot";
      if (!data.agent) {
        healthDot.classList.add("err");
        healthText.textContent = "未加载 Agent";
      } else if (data.agent === "sim_agent") {
        if (rosOk && videoOk) {
          healthDot.classList.add("ok");
          healthText.textContent = "sim 网关 + 头载相机正常";
        } else if (rosOk) {
          healthDot.classList.add("warn");
          healthText.textContent = "sim 网关正常 · 请打开仿真页以生成摄像头";
        } else {
          healthDot.classList.add("err");
          healthText.textContent = "sim 未连通 · 请先启动 tests/sim";
        }
      } else if (data.mode === "mock") {
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
      const host = data.robot_host || robot.robot_host || robot.ip;
      robotMeta.textContent = `agent ${data.agent || "?"} · ip ${host || "?"} · mode ${data.mode}`;
    } catch (err) {
      healthDot.className = "dot err";
      healthText.textContent = "health 请求失败";
      showToast(String(err.message || err), { title: "健康检查失败", kind: "err" });
    }
  }

  fillActions([]);
  refreshAgents();
  refreshHealth();
  setInterval(refreshHealth, 5000);

  return { refreshAgents, refreshHealth, fillActions, setStatus };
}
