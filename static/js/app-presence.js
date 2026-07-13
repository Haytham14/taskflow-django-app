(function () {
  const apiUrl = "/api/chat/presence/";
  const heartbeatInterval = 10000;
  const unreadInterval = 3000;
  const tabKey = `taskflow-presence-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  let timer = null;
  let unreadTimer = null;
  const unreadBadge = document.getElementById("global-chat-unread-badge");

  function csrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function activeTabs() {
    const now = Date.now();
    const tabs = JSON.parse(localStorage.getItem("taskflow-presence-tabs") || "{}");
    Object.keys(tabs).forEach((key) => {
      if (now - Number(tabs[key] || 0) > heartbeatInterval * 3) delete tabs[key];
    });
    return tabs;
  }

  function storeTabHeartbeat() {
    const tabs = activeTabs();
    tabs[tabKey] = Date.now();
    localStorage.setItem("taskflow-presence-tabs", JSON.stringify(tabs));
  }

  async function reportOnline() {
    storeTabHeartbeat();
    await fetch(apiUrl, {
      method: "POST",
      credentials: "same-origin",
      keepalive: true,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({ status: "online" }),
    });
  }

  async function refreshUnreadCount() {
    if (!unreadBadge || document.hidden) return;
    const response = await fetch("/api/chat/unread-count/", {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!response.ok) return;
    const data = await response.json();
    const total = Number(data.unread_count || 0);
    unreadBadge.textContent = total > 99 ? "99+" : String(total);
    unreadBadge.hidden = total === 0;
    unreadBadge.setAttribute(
      "aria-label",
      `${total} message${total > 1 ? "s" : ""} non lu${total > 1 ? "s" : ""}`
    );
  }

  function reportOffline() {
    const tabs = activeTabs();
    delete tabs[tabKey];
    localStorage.setItem("taskflow-presence-tabs", JSON.stringify(tabs));
    if (Object.keys(tabs).length || !navigator.sendBeacon) return;

    const data = new FormData();
    data.append("status", "offline");
    data.append("csrfmiddlewaretoken", csrfToken());
    navigator.sendBeacon(apiUrl, data);
  }

  reportOnline().catch(() => {});
  refreshUnreadCount().catch(() => {});
  timer = window.setInterval(() => reportOnline().catch(() => {}), heartbeatInterval);
  unreadTimer = window.setInterval(() => refreshUnreadCount().catch(() => {}), unreadInterval);

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshUnreadCount().catch(() => {});
  });

  window.addEventListener("taskflow:chat-unread-changed", () => {
    refreshUnreadCount().catch(() => {});
  });

  window.addEventListener("pagehide", () => {
    window.clearInterval(timer);
    window.clearInterval(unreadTimer);
    reportOffline();
  });
}());
