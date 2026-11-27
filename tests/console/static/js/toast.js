/**
 * Simple error/info toast bubbles (top-center).
 */
export function showToast(message, { title = "错误", kind = "err", durationMs = 8000 } = {}) {
  const host = document.getElementById("toast-host");
  if (!host) {
    window.alert(`${title}\n${message}`);
    return;
  }

  const el = document.createElement("div");
  el.className = `toast toast-${kind}`;
  el.setAttribute("role", "alert");

  const head = document.createElement("div");
  head.className = "toast-head";
  const h = document.createElement("strong");
  h.textContent = title;
  const close = document.createElement("button");
  close.type = "button";
  close.className = "toast-close";
  close.setAttribute("aria-label", "关闭");
  close.textContent = "×";
  head.append(h, close);

  const body = document.createElement("pre");
  body.className = "toast-body";
  body.textContent = String(message || "");

  el.append(head, body);
  host.appendChild(el);

  const remove = () => {
    el.classList.add("toast-out");
    setTimeout(() => el.remove(), 180);
  };
  close.addEventListener("click", remove);
  if (durationMs > 0) setTimeout(remove, durationMs);
}

export function formatDetail(detail) {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  try {
    return JSON.stringify(detail, null, 2);
  } catch {
    return String(detail);
  }
}
