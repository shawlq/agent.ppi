/**
 * Webviz-style mosaic debug board: binary-tree splits, panel select, close.
 * Panels are driven by snapshot.panels keys; render by type only (text|json|image).
 * Layout persisted in localStorage under debug.board.mosaic.v3.
 */

const STORAGE_KEY = "debug.board.mosaic.v3";
const MIN_RATIO = 0.15;
const MAX_RATIO = 0.85;

/** Fallback Select keys before the first snapshot arrives. */
const DEFAULT_PANEL_KEYS = [
  "cam",
  "df",
  "vlm",
  "context",
  "prompt",
  "llm",
  "reason",
  "actions_valid",
  "actions_history",
  "errors",
];

let _idSeq = 0;
function nextId(prefix = "n") {
  _idSeq += 1;
  return `${prefix}_${_idSeq}_${Date.now().toString(36)}`;
}

/** Fresh open: 2×2 mosaic — cam | df / vlm | actions_valid */
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
      second: { id: nextId("leaf"), type: "leaf", panel: "actions_valid" },
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

function pretty(v) {
  if (v == null) return "";
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch (_) {
    return String(v);
  }
}

export class DebugBoard {
  /**
   * @param {HTMLElement} host
   */
  constructor(host) {
    this.host = host;
    this.root = null;
    /** @type {Map<string, { el: HTMLElement, body: HTMLElement, titleLabel: HTMLElement, meta: HTMLElement, node: object }>} */
    this.leaves = new Map();
    this._lastSnap = null;
    this._openMenu = null;
    this._onDocClick = (ev) => this._handleDocClick(ev);
    this._build();
    document.addEventListener("click", this._onDocClick);
  }

  _panelKeys() {
    const panels = this._lastSnap?.panels;
    if (panels && typeof panels === "object") {
      const keys = Object.keys(panels);
      if (keys.length) return keys;
    }
    return DEFAULT_PANEL_KEYS;
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
    firstPane.style.flex = `${ratio} 1 0`;
    secondPane.style.flex = `${1 - ratio} 1 0`;

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
    titleLabel.textContent = node.panel || "Select panel";

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
    this._fillBody(body, node.panel, this._lastSnap?.panels?.[node.panel]);

    panel.appendChild(title);
    panel.appendChild(body);

    this.leaves.set(node.id, { el: panel, body, titleLabel, meta, node });

    if (this._lastSnap) this._paintLeaf(node.id, this._lastSnap);

    return panel;
  }

  /**
   * Scaffold body shell from panel type (or waiting state).
   * @param {HTMLElement} body
   * @param {string|null} panelKey
   * @param {object|null|undefined} panelDesc
   */
  _fillBody(body, panelKey, panelDesc) {
    body.innerHTML = "";
    if (!panelKey) {
      const empty = document.createElement("div");
      empty.className = "panel-empty";
      empty.textContent = "点击 ⋮ → Select 选择面板";
      body.appendChild(empty);
      return;
    }
    const type = panelDesc?.type;
    if (type === "image") {
      const img = document.createElement("img");
      img.alt = panelKey;
      img.dataset.panel = panelKey;
      body.appendChild(img);
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
        for (const key of this._panelKeys()) {
          const opt = document.createElement("button");
          opt.type = "button";
          opt.className = "panel-menu-item";
          if (node.panel === key) opt.classList.add("active");
          opt.textContent = key;
          opt.addEventListener("click", () => {
            this._selectPanel(node.id, key);
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

  _selectPanel(leafId, panelKey) {
    const entry = this.leaves.get(leafId);
    let node = entry?.node;
    if (!node) {
      walkLeaves(this.root, (n) => {
        if (n.id === leafId) node = n;
      });
    }
    if (!node) return;
    node.panel = panelKey;
    this._saveTree();

    if (entry) {
      entry.node = node;
      entry.titleLabel.textContent = panelKey;
      entry.el.dataset.panel = panelKey;
      this._fillBody(entry.body, panelKey, this._lastSnap?.panels?.[panelKey]);
      if (this._lastSnap) this._paintLeaf(leafId, this._lastSnap);
    } else {
      this._render();
    }
  }

  /**
   * Merge sparse panel patches into last snap; paint only keys present in this event.
   * @param {object} snap
   */
  applySnapshot(snap) {
    if (!snap) return;

    const incoming = snap.panels && typeof snap.panels === "object" ? snap.panels : {};
    const prev = this._lastSnap || { panels: {} };
    const mergedPanels = { ...(prev.panels || {}), ...incoming };

    this._lastSnap = {
      ...prev,
      ...snap,
      panels: mergedPanels,
    };

    const changedKeys = new Set(Object.keys(incoming));
    const sparse = snap.kind === "cam" || Object.keys(incoming).length < Object.keys(mergedPanels).length;

    for (const [leafId, entry] of this.leaves) {
      const panelKey = entry.node.panel;
      if (!panelKey) continue;
      if (sparse && !changedKeys.has(panelKey)) continue;
      this._paintLeaf(leafId, this._lastSnap);
    }
  }

  _paintLeaf(leafId, snap) {
    const entry = this.leaves.get(leafId);
    if (!entry) return;
    const panelKey = entry.node.panel;
    if (!panelKey) return;

    const desc = snap?.panels?.[panelKey];
    if (!desc || typeof desc !== "object") {
      this._ensureShell(entry, panelKey, null);
      this._setText(entry, "等待数据…");
      return;
    }

    const type = desc.type;
    this._ensureShell(entry, panelKey, desc);

    if (type === "image") {
      const img = entry.body.querySelector("img");
      const rev = typeof desc.rev === "number" ? desc.rev : 0;
      const srcBase = typeof desc.src === "string" ? desc.src : `/api/debug/image/${panelKey}`;
      if (img && rev > 0) {
        const url = `${srcBase}?t=${rev}`;
        if (!img.src.endsWith(`t=${rev}`)) {
          img.src = url;
        }
      }
      if (entry.meta) {
        entry.meta.textContent = rev > 0 ? `rev ${rev}` : "";
      }
      return;
    }

    if (type === "text") {
      this._setText(entry, typeof desc.value === "string" ? desc.value : pretty(desc.value));
    } else if (type === "json") {
      this._setText(entry, pretty(desc.value));
    } else {
      // Unknown type: dump whole descriptor.
      this._setText(entry, pretty(desc));
    }

    if (entry.meta && snap.round_id != null && panelKey !== "cam") {
      entry.meta.textContent = `#${snap.round_id}`;
    }
  }

  _ensureShell(entry, panelKey, desc) {
    const wantImage = desc?.type === "image";
    const hasImg = !!entry.body.querySelector("img");
    const hasPre = !!entry.body.querySelector("pre");
    if (wantImage && hasImg) return;
    if (!wantImage && hasPre && !hasImg) return;
    this._fillBody(entry.body, panelKey, desc);
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
}
