/**
 * Webviz-style mosaic debug board: binary-tree splits, panel select, close.
 * Layout persisted in localStorage under debug.board.mosaic.
 */

const STORAGE_KEY = "debug.board.mosaic.v2";
const MIN_RATIO = 0.15;
const MAX_RATIO = 0.85;

const PANEL_DEFS = [
  { id: "cam", title: "Cam" },
  { id: "df", title: "DF" },
  { id: "vlm", title: "VLM" },
  { id: "context", title: "Context" },
  { id: "prompt", title: "Prompt" },
  { id: "llm", title: "LLM" },
  { id: "actions", title: "Actions" },
];

const PANEL_TITLE = Object.fromEntries(PANEL_DEFS.map((p) => [p.id, p.title]));

let _idSeq = 0;
function nextId(prefix = "n") {
  _idSeq += 1;
  return `${prefix}_${_idSeq}_${Date.now().toString(36)}`;
}

/** Fresh open: 2×2 mosaic — Cam | DF / VLM | Actions */
function defaultTree() {
  return {
    id: nextId("split"),
    type: "split",
    direction: "col",
    ratio: 0.5,
    first: {
      id: nextId("split"),
      type: "split",
      direction: "row",
      ratio: 0.5,
      first: { id: nextId("leaf"), type: "leaf", panel: "cam" },
      second: { id: nextId("leaf"), type: "leaf", panel: "df" },
    },
    second: {
      id: nextId("split"),
      type: "split",
      direction: "row",
      ratio: 0.5,
      first: { id: nextId("leaf"), type: "leaf", panel: "vlm" },
      second: { id: nextId("leaf"), type: "leaf", panel: "actions" },
    },
  };
}

function cloneTree(node) {
  if (!node) return null;
  if (node.type === "leaf") {
    return { id: node.id || nextId("leaf"), type: "leaf", panel: node.panel ?? null };
  }
  return {
    id: node.id || nextId("split"),
    type: "split",
    direction: node.direction === "col" ? "col" : "row",
    ratio: typeof node.ratio === "number" ? node.ratio : 0.5,
    first: cloneTree(node.first),
    second: cloneTree(node.second),
  };
}

function findPath(root, leafId, path = []) {
  if (!root) return null;
  if (root.type === "leaf") {
    return root.id === leafId ? path : null;
  }
  const left = findPath(root.first, leafId, [...path, { node: root, side: "first" }]);
  if (left) return left;
  return findPath(root.second, leafId, [...path, { node: root, side: "second" }]);
}

function countLeaves(node) {
  if (!node) return 0;
  if (node.type === "leaf") return 1;
  return countLeaves(node.first) + countLeaves(node.second);
}

function walkLeaves(node, fn) {
  if (!node) return;
  if (node.type === "leaf") {
    fn(node);
    return;
  }
  walkLeaves(node.first, fn);
  walkLeaves(node.second, fn);
}

export class DebugBoard {
  /**
   * @param {HTMLElement} host
   */
  constructor(host) {
    this.host = host;
    this.root = null;
    /** @type {Map<string, { el: HTMLElement, body: HTMLElement, titleLabel: HTMLElement, node: object }>} */
    this.leaves = new Map();
    this._camRev = -1;
    this._dfRev = -1;
    this._lastSnap = null;
    this._openMenu = null;
    this._onDocClick = (ev) => this._handleDocClick(ev);
    this._build();
    document.addEventListener("click", this._onDocClick);
  }

  _build() {
    this.host.classList.add("mosaic-root");
    this.host.innerHTML = "";
    this.leaves.clear();
    const saved = this._loadTree();
    this.root = saved || defaultTree();
    if (!saved) this._saveTree();
    this._render();
    window.addEventListener("beforeunload", () => this._saveTree());
  }

  _loadTree() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || (parsed.type !== "leaf" && parsed.type !== "split")) return null;
      const tree = cloneTree(parsed);
      // Reject empty / corrupt trees.
      if (!tree || countLeaves(tree) < 1) return null;
      return tree;
    } catch (_) {
      return null;
    }
  }

  _saveTree() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.root));
    } catch (_) {
      /* ignore */
    }
  }

  _render() {
    this._closeMenu();
    this.host.innerHTML = "";
    this.leaves.clear();
    const el = this._renderNode(this.root);
    if (el) this.host.appendChild(el);
  }

  /**
   * @param {object} node
   * @returns {HTMLElement}
   */
  _renderNode(node) {
    if (node.type === "leaf") return this._renderLeaf(node);
    return this._renderSplit(node);
  }

  _renderSplit(node) {
    const wrap = document.createElement("div");
    wrap.className = `mosaic-split mosaic-${node.direction === "col" ? "col" : "row"}`;
    wrap.dataset.id = node.id;

    const firstPane = document.createElement("div");
    firstPane.className = "mosaic-pane";
    const secondPane = document.createElement("div");
    secondPane.className = "mosaic-pane";

    const ratio = Math.min(MAX_RATIO, Math.max(MIN_RATIO, node.ratio ?? 0.5));
    node.ratio = ratio;
    if (node.direction === "col") {
      firstPane.style.flex = `${ratio} 1 0`;
      secondPane.style.flex = `${1 - ratio} 1 0`;
    } else {
      firstPane.style.flex = `${ratio} 1 0`;
      secondPane.style.flex = `${1 - ratio} 1 0`;
    }

    firstPane.appendChild(this._renderNode(node.first));
    secondPane.appendChild(this._renderNode(node.second));

    const sash = document.createElement("div");
    sash.className = `mosaic-sash mosaic-sash-${node.direction === "col" ? "col" : "row"}`;
    sash.title = "拖动调整比例";
    this._bindSash(sash, wrap, node, firstPane, secondPane);

    wrap.appendChild(firstPane);
    wrap.appendChild(sash);
    wrap.appendChild(secondPane);
    return wrap;
  }

  _bindSash(sash, wrap, node, firstPane, secondPane) {
    let dragging = false;

    sash.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      dragging = true;
      sash.setPointerCapture(ev.pointerId);
      sash.classList.add("active");
      ev.preventDefault();
      ev.stopPropagation();
    });

    sash.addEventListener("pointermove", (ev) => {
      if (!dragging) return;
      const rect = wrap.getBoundingClientRect();
      let ratio;
      if (node.direction === "col") {
        const y = ev.clientY - rect.top;
        ratio = y / rect.height;
      } else {
        const x = ev.clientX - rect.left;
        ratio = x / rect.width;
      }
      ratio = Math.min(MAX_RATIO, Math.max(MIN_RATIO, ratio));
      node.ratio = ratio;
      firstPane.style.flex = `${ratio} 1 0`;
      secondPane.style.flex = `${1 - ratio} 1 0`;
    });

    const end = (ev) => {
      if (!dragging) return;
      dragging = false;
      sash.classList.remove("active");
      try {
        sash.releasePointerCapture(ev.pointerId);
      } catch (_) {
        /* ignore */
      }
      this._saveTree();
    };
    sash.addEventListener("pointerup", end);
    sash.addEventListener("pointercancel", end);
  }

  _renderLeaf(node) {
    const panel = document.createElement("div");
    panel.className = "debug-panel";
    panel.dataset.leafId = node.id;
    if (node.panel) panel.dataset.panel = node.panel;

    const title = document.createElement("div");
    title.className = "panel-titlebar";

    const titleLabel = document.createElement("span");
    titleLabel.className = "panel-title";
    titleLabel.textContent = node.panel ? PANEL_TITLE[node.panel] || node.panel : "Select panel";

    const meta = document.createElement("span");
    meta.className = "hint";
    meta.dataset.meta = "";

    const menuBtn = document.createElement("button");
    menuBtn.type = "button";
    menuBtn.className = "panel-menu-btn";
    menuBtn.setAttribute("aria-label", "面板菜单");
    menuBtn.textContent = "⋮";
    menuBtn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      this._toggleMenu(menuBtn, node);
    });

    title.appendChild(titleLabel);
    title.appendChild(meta);
    title.appendChild(menuBtn);

    const body = document.createElement("div");
    body.className = "panel-body";
    this._fillBody(body, node.panel);

    panel.appendChild(title);
    panel.appendChild(body);

    this.leaves.set(node.id, { el: panel, body, titleLabel, meta, node });

    if (this._lastSnap) this._paintLeaf(node.id, this._lastSnap);

    return panel;
  }

  _fillBody(body, panelType) {
    body.innerHTML = "";
    if (!panelType) {
      const empty = document.createElement("div");
      empty.className = "panel-empty";
      empty.textContent = "点击 ⋮ → Select 选择面板";
      body.appendChild(empty);
      return;
    }
    if (panelType === "cam" || panelType === "df") {
      const img = document.createElement("img");
      img.alt = panelType;
      img.dataset.kind = panelType;
      body.appendChild(img);
      return;
    }
    if (panelType === "actions") {
      return;
    }
    const pre = document.createElement("pre");
    pre.textContent = "等待数据…";
    body.appendChild(pre);
  }

  _toggleMenu(btn, node) {
    if (this._openMenu && this._openMenu.leafId === node.id) {
      this._closeMenu();
      return;
    }
    this._closeMenu();

    const menu = document.createElement("div");
    menu.className = "panel-menu";
    menu.addEventListener("click", (ev) => ev.stopPropagation());

    const items = [
      { label: "Split Vertical", action: () => this._split(node.id, "row") },
      { label: "Split Horizontal", action: () => this._split(node.id, "col") },
      { label: "Close", action: () => this._close(node.id), disabled: countLeaves(this.root) <= 1 },
      { label: "Select", action: null, submenu: true },
    ];

    for (const item of items) {
      if (item.submenu) {
        const selectBtn = document.createElement("button");
        selectBtn.type = "button";
        selectBtn.className = "panel-menu-item has-sub";
        selectBtn.textContent = "Select ▸";
        const sub = document.createElement("div");
        sub.className = "panel-submenu";
        for (const def of PANEL_DEFS) {
          const opt = document.createElement("button");
          opt.type = "button";
          opt.className = "panel-menu-item";
          if (node.panel === def.id) opt.classList.add("active");
          opt.textContent = def.title;
          opt.addEventListener("click", () => {
            this._selectPanel(node.id, def.id);
            this._closeMenu();
          });
          sub.appendChild(opt);
        }
        const wrap = document.createElement("div");
        wrap.className = "panel-menu-select";
        wrap.appendChild(selectBtn);
        wrap.appendChild(sub);
        selectBtn.addEventListener("click", () => {
          wrap.classList.toggle("open");
          if (wrap.classList.contains("open")) {
            // Flip submenu left if it would overflow the viewport.
            requestAnimationFrame(() => {
              const subRect = sub.getBoundingClientRect();
              if (subRect.right > window.innerWidth - 8) {
                sub.style.left = "auto";
                sub.style.right = "100%";
                sub.style.marginLeft = "0";
                sub.style.marginRight = "2px";
              }
            });
          }
        });
        menu.appendChild(wrap);
        continue;
      }

      const btnEl = document.createElement("button");
      btnEl.type = "button";
      btnEl.className = "panel-menu-item";
      btnEl.textContent = item.label;
      if (item.disabled) {
        btnEl.disabled = true;
      } else {
        btnEl.addEventListener("click", () => {
          this._closeMenu();
          item.action();
        });
      }
      menu.appendChild(btnEl);
    }

    const rect = btn.getBoundingClientRect();
    menu.style.position = "fixed";
    menu.style.top = `${rect.bottom + 4}px`;
    menu.style.left = `${Math.min(rect.right - 180, window.innerWidth - 190)}px`;
    document.body.appendChild(menu);
    this._openMenu = { el: menu, leafId: node.id };
  }

  _closeMenu() {
    if (this._openMenu) {
      this._openMenu.el.remove();
      this._openMenu = null;
    }
  }

  _handleDocClick(ev) {
    if (!this._openMenu) return;
    if (this._openMenu.el.contains(ev.target)) return;
    if (ev.target.closest?.(".panel-menu-btn")) return;
    this._closeMenu();
  }

  /**
   * Replace leaf with a split; original stays on first side, new empty leaf on second.
   * @param {string} leafId
   * @param {"row"|"col"} direction
   */
  _split(leafId, direction) {
    const path = findPath(this.root, leafId);
    if (path === null && this.root?.id !== leafId) return;

    const getLeaf = () => {
      if (this.root.type === "leaf" && this.root.id === leafId) return this.root;
      const last = path[path.length - 1];
      return last.node[last.side];
    };

    const leaf = this.root.type === "leaf" && this.root.id === leafId ? this.root : getLeaf();
    if (!leaf || leaf.type !== "leaf") return;

    const newLeaf = { id: nextId("leaf"), type: "leaf", panel: null };
    const split = {
      id: nextId("split"),
      type: "split",
      direction,
      ratio: 0.5,
      first: leaf,
      second: newLeaf,
    };

    if (this.root.type === "leaf" && this.root.id === leafId) {
      this.root = split;
    } else {
      const last = path[path.length - 1];
      last.node[last.side] = split;
    }

    this._saveTree();
    this._render();
  }

  _close(leafId) {
    if (countLeaves(this.root) <= 1) return;

    if (this.root.type === "leaf") return;

    const path = findPath(this.root, leafId);
    if (!path || path.length === 0) return;

    const parentInfo = path[path.length - 1];
    const parent = parentInfo.node;
    const siblingSide = parentInfo.side === "first" ? "second" : "first";
    const sibling = parent[siblingSide];

    if (path.length === 1) {
      this.root = sibling;
    } else {
      const grand = path[path.length - 2];
      grand.node[grand.side] = sibling;
    }

    this._saveTree();
    this._render();
  }

  _selectPanel(leafId, panelType) {
    const entry = this.leaves.get(leafId);
    let node = entry?.node;
    if (!node) {
      walkLeaves(this.root, (n) => {
        if (n.id === leafId) node = n;
      });
    }
    if (!node) return;
    node.panel = panelType;
    this._saveTree();

    if (entry) {
      entry.node = node;
      entry.titleLabel.textContent = PANEL_TITLE[panelType] || panelType;
      entry.el.dataset.panel = panelType;
      this._fillBody(entry.body, panelType);
      if (this._lastSnap) this._paintLeaf(leafId, this._lastSnap);
    } else {
      this._render();
    }
  }

  /**
   * Merge sparse events (e.g. kind:"cam") into last snap so text panels
   * keep their last round content until the next kind:"round" update.
   * @param {object} snap
   */
  applySnapshot(snap) {
    if (!snap) return;

    // SSE cam events are sparse ({kind,cam_rev,…}); merged /api/debug/latest may
    // keep kind:"cam" but still carry round fields — detect by payload shape.
    const camOnly =
      snap.kind === "cam" &&
      snap.prompt === undefined &&
      snap.llm_raw === undefined &&
      snap.vlm_raw === undefined;

    const prev = this._lastSnap || {};
    if (camOnly) {
      this._lastSnap = {
        ...prev,
        cam_rev: snap.cam_rev,
        df_rev: snap.df_rev ?? prev.df_rev,
        stamp: snap.stamp,
      };
    } else {
      this._lastSnap = { ...prev, ...snap };
    }

    if (typeof this._lastSnap.cam_rev === "number") this._camRev = this._lastSnap.cam_rev;
    if (typeof this._lastSnap.df_rev === "number") this._dfRev = this._lastSnap.df_rev;

    for (const [leafId, entry] of this.leaves) {
      const panel = entry.node.panel;
      if (!panel) continue;
      if (panel === "cam") {
        if (typeof snap.cam_rev === "number") this._paintLeaf(leafId, this._lastSnap);
        continue;
      }
      if (panel === "df") {
        if (!camOnly) this._paintLeaf(leafId, this._lastSnap);
        continue;
      }
      // Text / actions: keep previous DOM until a non-cam-only (round) update.
      if (!camOnly) this._paintLeaf(leafId, this._lastSnap);
    }
  }

  _paintLeaf(leafId, snap) {
    const entry = this.leaves.get(leafId);
    if (!entry) return;
    const panel = entry.node.panel;
    if (!panel) return;

    if (panel === "cam") {
      const img = entry.body.querySelector("img");
      if (img && typeof snap.cam_rev === "number" && snap.cam_rev > 0) {
        const url = `/api/debug/image/cam?t=${snap.cam_rev}`;
        if (!img.src.endsWith(`t=${snap.cam_rev}`)) {
          img.src = url;
        }
      }
      return;
    }

    if (panel === "df") {
      const img = entry.body.querySelector("img");
      if (img && typeof snap.df_rev === "number" && snap.df_rev > 0) {
        const url = `/api/debug/image/df?t=${snap.df_rev}`;
        if (!img.src.endsWith(`t=${snap.df_rev}`)) {
          img.src = url;
        }
      }
      return;
    }

    if (panel === "vlm") {
      this._setText(entry, pretty(snap.vlm_parsed || snap.vlm_raw));
      return;
    }
    if (panel === "context") {
      this._setText(entry, pretty(snap.context));
      return;
    }
    if (panel === "prompt") {
      this._setText(entry, snap.prompt || "");
      return;
    }
    if (panel === "llm") {
      this._setText(entry, snap.llm_raw || "");
      return;
    }
    if (panel === "actions") {
      this._setActions(entry, snap);
      if (entry.meta) entry.meta.textContent = snap.round_id ? `#${snap.round_id}` : "";
    }
  }

  _setText(entry, text) {
    let pre = entry.body.querySelector("pre");
    if (!pre) {
      entry.body.innerHTML = "";
      pre = document.createElement("pre");
      entry.body.appendChild(pre);
    }
    pre.textContent = text || "（空）";
  }

  _setActions(entry, snap) {
    const body = entry.body;
    body.innerHTML = "";
    const current = document.createElement("div");
    current.className = "actions-block";
    current.innerHTML = `<h4>本轮 #${snap.round_id ?? "-"}</h4>`;
    if (snap.reason) {
      const why = document.createElement("pre");
      why.className = "actions-reason";
      why.textContent = "reason: " + snap.reason;
      current.appendChild(why);
    }
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
      if (h.reason) {
        const why = document.createElement("pre");
        why.className = "actions-reason";
        why.textContent = "reason: " + h.reason;
        block.appendChild(why);
      }
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
