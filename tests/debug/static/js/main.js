import { DebugBoard } from "./DebugBoard.js";

const agentSelect = document.getElementById("agent-select");
const btnConnect = document.getElementById("btn-connect");
const btnDisconnect = document.getElementById("btn-disconnect");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const boardHost = document.getElementById("board-host");

const board = new DebugBoard(boardHost);
let es = null;

function setStatus(text, kind) {
  statusText.textContent = text;
  statusDot.classList.remove("on", "err");
  if (kind) statusDot.classList.add(kind);
}

function setConnected(on) {
  btnConnect.disabled = on;
  btnDisconnect.disabled = !on;
  agentSelect.disabled = on;
}

async function loadAgents() {
  const res = await fetch("/api/agents");
  const data = await res.json();
  const agents = data.agents || [];
  agentSelect.innerHTML = "";
  for (const a of agents) {
    const opt = document.createElement("option");
    opt.value = a.name;
    opt.textContent = a.name;
    agentSelect.appendChild(opt);
  }
  if ([...agentSelect.options].some((o) => o.value === "sim_agent")) {
    agentSelect.value = "sim_agent";
  }
}

function startSSE() {
  stopSSE();
  es = new EventSource("/api/debug/stream");
  es.onmessage = (ev) => {
    try {
      const snap = JSON.parse(ev.data);
      board.applySnapshot(snap);
      if (snap.kind === "round") {
        setStatus(`已连接 · round #${snap.round_id}`, "on");
      }
    } catch (err) {
      console.error("sse parse", err);
    }
  };
  es.onerror = () => {
    /* browser will retry */
  };
}

function stopSSE() {
  if (es) {
    es.close();
    es = null;
  }
}

async function connect() {
  const agent = agentSelect.value || "sim_agent";
  setStatus(`连接中 ${agent}…`);
  btnConnect.disabled = true;
  try {
    const res = await fetch("/api/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || res.statusText);
    }
    setConnected(true);
    setStatus(`已连接 · ${agent}`, "on");
    startSSE();
    const latest = await fetch("/api/debug/latest").then((r) => r.json());
    if (latest.snapshot) board.applySnapshot(latest.snapshot);
  } catch (err) {
    setConnected(false);
    setStatus(`连接失败: ${err.message || err}`, "err");
  }
}

async function disconnect() {
  stopSSE();
  try {
    await fetch("/api/disconnect", { method: "POST" });
  } catch (_) {
    /* ignore */
  }
  setConnected(false);
  setStatus("未连接");
}

btnConnect.addEventListener("click", connect);
btnDisconnect.addEventListener("click", disconnect);

loadAgents()
  .then(async () => {
    const st = await fetch("/api/status").then((r) => r.json());
    if (st.running) {
      setConnected(true);
      setStatus(`已连接 · ${st.agent || "?"}`, "on");
      startSSE();
    }
  })
  .catch((err) => {
    setStatus(`启动失败: ${err.message || err}`, "err");
  });
