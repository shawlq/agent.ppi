/**
 * Right-side panel: focus height, action list, queue view.
 */
export function setupUI({ actions, uiConfig, cameraFocus, queue }) {
  const focusInput = document.getElementById("focus-height");
  const actionsList = document.getElementById("actions-list");
  const actionsToggle = document.getElementById("actions-toggle");
  const actionsBody = document.getElementById("actions-body");
  const queueList = document.getElementById("queue-list");
  const queueEmpty = document.getElementById("queue-empty");
  const queueClear = document.getElementById("queue-clear");

  const focusH = uiConfig.focus_height_m ?? 1.7;
  focusInput.value = String(focusH);
  cameraFocus.setFocusHeight(focusH);

  focusInput.addEventListener("change", () => {
    const v = Number(focusInput.value);
    if (!Number.isFinite(v) || v <= 0) {
      focusInput.value = String(cameraFocus.getFocusHeight());
      return;
    }
    cameraFocus.setFocusHeight(v);
  });

  actionsToggle.addEventListener("click", () => {
    const open = actionsToggle.getAttribute("aria-expanded") === "true";
    actionsToggle.setAttribute("aria-expanded", open ? "false" : "true");
    actionsBody.classList.toggle("collapsed", open);
  });

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

  // initial empty state
  queue.onChange(queue.snapshot);
}
