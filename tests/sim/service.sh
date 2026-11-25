#!/usr/bin/env bash
# PuppyPi 3D sim service wrapper
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8765}"
PID_FILE="${PID_FILE:-$ROOT/.uvicorn.pid}"
LOG_FILE="${LOG_FILE:-$ROOT/.uvicorn.log}"

CMD=(uvicorn server:app --reload --host "$HOST" --port "$PORT")

usage() {
  echo "Usage: $0 {start|stop|restart|status|run}"
  echo "  start   background start (default)"
  echo "  run     foreground (Ctrl+C to stop)"
  echo "  stop    stop background process / free PORT"
  echo "  restart stop then start"
  echo "  status  show whether service is running"
  echo "Env: HOST=$HOST PORT=$PORT"
}

pids_on_port() {
  local pids=""
  if command -v ss >/dev/null 2>&1; then
    pids="$(ss -tlnp "sport = :${PORT}" 2>/dev/null \
      | grep -oE 'pid=[0-9]+' \
      | cut -d= -f2 \
      | sort -u \
      | tr '\n' ' ' || true)"
  fi
  if [[ -z "${pids// }" ]] && command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true)"
  fi
  if [[ -z "${pids// }" ]] && command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "${PORT}/tcp" 2>/dev/null | tr -s ' ' || true)"
  fi
  echo "$pids"
}

pidfile_alive() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$pid"
      return 0
    fi
  fi
  return 1
}

is_running() {
  local pid
  if pid="$(pidfile_alive)"; then
    return 0
  fi
  local port_pids
  port_pids="$(pids_on_port)"
  [[ -n "${port_pids// }" ]]
}

do_start() {
  if is_running; then
    local pid
    pid="$(pidfile_alive || true)"
    if [[ -z "${pid}" ]]; then
      pid="$(pids_on_port | awk '{print $1}')"
    fi
    echo "already running pid=${pid:-?}  http://${HOST}:${PORT}/"
    return 0
  fi
  rm -f "$PID_FILE"
  : >"$LOG_FILE"
  nohup "${CMD[@]}" >>"$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" >"$PID_FILE"

  # --reload re-execs; wait until port is listening or fail
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 0.3
    if [[ -n "$(pids_on_port)" ]]; then
      # Prefer listener pid in pid file if parent already exited
      local listen_pid
      listen_pid="$(pids_on_port | awk '{print $1}')"
      if ! kill -0 "$pid" 2>/dev/null; then
        echo "$listen_pid" >"$PID_FILE"
      fi
      echo "started pid=$(cat "$PID_FILE")  http://${HOST}:${PORT}/"
      echo "log: $LOG_FILE"
      return 0
    fi
    # Parent died early with bind error
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
  done

  echo "failed to start; see $LOG_FILE" >&2
  if [[ -f "$LOG_FILE" ]]; then
    tail -n 20 "$LOG_FILE" >&2 || true
  fi
  rm -f "$PID_FILE"
  return 1
}

do_stop() {
  local pids=""
  local pid
  if pid="$(pidfile_alive)"; then
    pids="$pid"
  fi
  pids="$pids $(pids_on_port)"
  pids="$(echo "$pids" | tr ' ' '\n' | grep -E '^[0-9]+$' | sort -u | tr '\n' ' ' || true)"

  if [[ -z "${pids// }" ]]; then
    rm -f "$PID_FILE"
    echo "not running"
    return 0
  fi

  echo "stopping pids: $pids"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  sleep 0.4
  local left
  left="$(pids_on_port)"
  if [[ -n "${left// }" ]]; then
    # shellcheck disable=SC2086
    kill -9 $left 2>/dev/null || true
    sleep 0.2
  fi
  rm -f "$PID_FILE"
  if [[ -n "$(pids_on_port)" ]]; then
    echo "warn: port $PORT still busy: $(pids_on_port)" >&2
    return 1
  fi
  echo "stopped"
}

do_status() {
  local pid
  if pid="$(pidfile_alive)"; then
    echo "running pid=$pid  http://${HOST}:${PORT}/"
    return 0
  fi
  local port_pids
  port_pids="$(pids_on_port)"
  if [[ -n "${port_pids// }" ]]; then
    echo "running (no pidfile) pids=$port_pids  http://${HOST}:${PORT}/"
    return 0
  fi
  echo "stopped"
  return 1
}

do_run() {
  # Free port if a previous background instance is leftover
  if [[ -n "$(pids_on_port)" ]]; then
    echo "port $PORT busy; stopping existing listeners first"
    do_stop
  fi
  exec "${CMD[@]}"
}

action="${1:-start}"
case "$action" in
  start) do_start ;;
  stop) do_stop ;;
  restart) do_stop; do_start ;;
  status) do_status ;;
  run) do_run ;;
  -h|--help|help) usage ;;
  *)
    usage >&2
    exit 2
    ;;
esac
