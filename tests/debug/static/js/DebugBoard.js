/**
 * Draggable / resizable debug windows. Layout persisted in localStorage.
 */

const STORAGE_KEY = "debug.board.layout";
const MIN_W = 220;
const MIN_H = 140;

const PANEL_DEFS = [
  { id: "cam", title: "Cam" },
  { id: "df", title: "DF" },
  { id: "vlm", title: "VLM" },
  { id: "context", title: "Context" },
  { id: "prompt", title: "Prompt" },
  { id: "llm", title: "LLM" },
  { id: "actions", title: "Actions" },
];

function defaultLayout(hostW, hostH) {
  const cols = 4;
  const rows = 2;
  const gap = 10;
  const pad = 10;
  const cellW = Math.floor((hostW - pad * 2 - gap * (cols - 1)) / cols);
  const cellH = Math.floor((hostH - pad * 2 - gap * (rows - 1)) / rows);
  const layout = {};
  PANEL_DEFS.forEach((p, i) => {
    const c = i % cols;
    const r = Math.floor(i / cols);
    layout[p.id] = {
      x: pad + c * (cellW + gap),
      y: pad + r * (cellH + gap),
      w: cellW,
      h: i === 6 ? Math.min(cellH, hostH - pad * 2) : cellH,
    };
  });
  // 7th panel spans remaining width on row 2 if needed
  if (layout.actions) {
    layout.actions.w = Math.min(cellW * 2 + gap, hostW - layout.actions.x - pad);
  }
  return layout;
}

export class DebugBoard {
  /**
   * @param {HTMLElement} host
   */
  constructor(host) {
    this.host = host;
    this.windows = new Map();
    this._layout = {};
    this._camRev = -1;
    this._dfRev = -1;
    this._build();
  }

  _build() {
    const rect = this.host.getBoundingClientRect();
    const saved = this._loadLayout();
    this._layout = saved || defaultLayout(rect.width || 1200, rect.height || 700);

    for (const def of PANEL_DEFS) {
      const win = document.createElement("div");
      win.className = "debug-win";
      win.dataset.id = def.id;

      const title = document.createElement("div");
      title.className = "win-title";
      title.innerHTML = `<span>${def.title}</span><span class="hint" data-meta></span>`;

      const body = document.createElement("div");
      body.className = "win-body";
      if (def.id === "cam" || def.id === "df") {
        const img = document.createElement("img");
        img.alt = def.id;
        img.dataset.kind = def.id;
        body.appendChild(img);
      } else {
        const pre = document.createElement("pre");
        pre.textContent = "等待数据…";
        body.appendChild(pre);
      }

      const resize = document.createElement("div");
      resize.className = "win-resize";

      win.appendChild(title);
      win.appendChild(body);
      win.appendChild(resize);
      this.host.appendChild(win);

      this._applyGeom(win, this._layout[def.id]);
      this._bindDrag(win, title);
      this._bindResize(win, resize);
      win.addEventListener("pointerdown", () => this._focus(win));

      this.windows.set(def.id, { el: win, body, title });
    }
  }

  _focus(win) {
    for (const { el } of this.windows.values()) el.classList.remove("active");
    win.classList.add("active");
  }

  _applyGeom(win, g) {
    if (!g) return;
    win.style.left = `${g.x}px`;
    win.style.top = `${g.y}px`;
    win.style.width = `${g.w}px`;
    win.style.height = `${g.h}px`;
  }

  _readGeom(win) {
    return {
      x: parseFloat(win.style.left) || 0,
      y: parseFloat(win.style.top) || 0,
      w: win.offsetWidth,
      h: win.offsetHeight,
    };
  }

  _saveLayout() {
    const layout = {};
    for (const [id, { el }] of this.windows) {
      layout[id] = this._readGeom(el);
    }
    this._layout = layout;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
    } catch (_) {
      /* ignore */
    }
  }

  _loadLayout() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  _bindDrag(win, handle) {
    let dragging = false;
    let sx = 0;
    let sy = 0;
    let ox = 0;
    let oy = 0;

    handle.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      dragging = true;
      handle.setPointerCapture(ev.pointerId);
      sx = ev.clientX;
      sy = ev.clientY;
      const g = this._readGeom(win);
      ox = g.x;
      oy = g.y;
      this._focus(win);
      ev.preventDefault();
    });
    handle.addEventListener("pointermove", (ev) => {
      if (!dragging) return;
      const dx = ev.clientX - sx;
      const dy = ev.clientY - sy;
      win.style.left = `${Math.max(0, ox + dx)}px`;
      win.style.top = `${Math.max(0, oy + dy)}px`;
    });
    const end = (ev) => {
      if (!dragging) return;
      dragging = false;
      try {
        handle.releasePointerCapture(ev.pointerId);
      } catch (_) {
        /* ignore */
      }
      this._saveLayout();
    };
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  }

  _bindResize(win, handle) {
    let resizing = false;
    let sx = 0;
    let sy = 0;
    let ow = 0;
    let oh = 0;

    handle.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      resizing = true;
      handle.setPointerCapture(ev.pointerId);
      sx = ev.clientX;
      sy = ev.clientY;
      const g = this._readGeom(win);
      ow = g.w;
      oh = g.h;
      this._focus(win);
      ev.preventDefault();
      ev.stopPropagation();
    });
    handle.addEventListener("pointermove", (ev) => {
      if (!resizing) return;
      const w = Math.max(MIN_W, ow + (ev.clientX - sx));
      const h = Math.max(MIN_H, oh + (ev.clientY - sy));
      win.style.width = `${w}px`;
      win.style.height = `${h}px`;
    });
    const end = (ev) => {
      if (!resizing) return;
      resizing = false;
      try {
        handle.releasePointerCapture(ev.pointerId);
      } catch (_) {
        /* ignore */
      }
      this._saveLayout();
    };
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
  }

  /**
   * @param {object} snap
   */
  applySnapshot(snap) {
    if (!snap) return;
    if (typeof snap.cam_rev === "number" && snap.cam_rev !== this._camRev) {
      this._camRev = snap.cam_rev;
      const img = this.windows.get("cam")?.body.querySelector("img");
      if (img) img.src = `/api/debug/image/cam?t=${snap.cam_rev}`;
    }
    if (snap.kind === "round" || snap.round_id) {
      if (typeof snap.df_rev === "number" && snap.df_rev !== this._dfRev) {
        this._dfRev = snap.df_rev;
        const img = this.windows.get("df")?.body.querySelector("img");
        if (img) img.src = `/api/debug/image/df?t=${snap.df_rev}`;
      }
      this._setText("vlm", pretty(snap.vlm_parsed || snap.vlm_raw));
      this._setText("context", pretty(snap.context));
      this._setText("prompt", snap.prompt || "");
      this._setText("llm", snap.llm_raw || "");
      this._setActions(snap);
      const meta = this.windows.get("actions")?.title.querySelector("[data-meta]");
      if (meta) meta.textContent = snap.round_id ? `#${snap.round_id}` : "";
    }
  }

  _setText(id, text) {
    const pre = this.windows.get(id)?.body.querySelector("pre");
    if (pre) pre.textContent = text || "（空）";
  }

  _setActions(snap) {
    const body = this.windows.get("actions")?.body;
    if (!body) return;
    body.innerHTML = "";
    const current = document.createElement("div");
    current.className = "actions-block";
    current.innerHTML = `<h4>本轮 #${snap.round_id ?? "-"}</h4>`;
    const pre = document.createElement("pre");
    pre.textContent = pretty(snap.actions_valid || []);
    current.appendChild(pre);
    if (Array.isArray(snap.errors) && snap.errors.length) {
      const err = document.createElement("pre");
      err.style.color = "#ef5350";
      err.textContent = "errors:\n" + snap.errors.join("\n");
      current.appendChild(err);
    }
    body.appendChild(current);

    const hist = Array.isArray(snap.actions_history) ? snap.actions_history : [];
    for (const h of hist) {
      if (h.round_id === snap.round_id) continue;
      const block = document.createElement("div");
      block.className = "actions-block";
      block.innerHTML = `<h4>历史 #${h.round_id}</h4>`;
      const p = document.createElement("pre");
      p.textContent = pretty(h.actions || []);
      block.appendChild(p);
      body.appendChild(block);
    }
  }
}

function pretty(v) {
  if (v == null) return "";
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch (_) {
    return String(v);
  }
}
