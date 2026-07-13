(function () {
  const root = document.getElementById("task-calendar");
  if (!root) return;

  const apiUrl = root.dataset.apiUrl;
  const createUrl = root.dataset.createUrl;
  const canCreate = root.dataset.canCreate === "true";
  const content = document.getElementById("calendar-content");
  const loading = document.getElementById("calendar-loading");
  const periodLabel = document.getElementById("calendar-period-label");
  const searchInput = document.getElementById("calendar-search");
  const filterIds = [
    "calendar-project-filter",
    "calendar-assignee-filter",
    "calendar-priority-filter",
    "calendar-status-filter",
  ];
  const filters = filterIds.map((id) => document.getElementById(id));
  const modal = document.getElementById("calendar-day-modal");
  const modalBackdrop = document.getElementById("calendar-modal-backdrop");
  const modalTitle = document.getElementById("calendar-modal-title");
  const modalList = document.getElementById("calendar-modal-list");
  let lastPayload = null;
  let searchTimer = null;
  const parameters = new URLSearchParams(window.location.search);
  const view = "month";
  let anchorDate = parseDate(parameters.get("date")) || startOfDay(new Date());

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function startOfDay(value) {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }

  function parseDate(value) {
    if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const [year, month, day] = value.split("-").map(Number);
    const parsed = new Date(year, month - 1, day);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function addDays(value, amount) {
    const result = new Date(value);
    result.setDate(result.getDate() + amount);
    return result;
  }

  function formatDate(value) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function sameDay(first, second) {
    return formatDate(first) === formatDate(second);
  }

  function startOfWeek(value) {
    const day = value.getDay() || 7;
    return addDays(startOfDay(value), 1 - day);
  }

  function currentRange() {
    return {
      start: new Date(anchorDate.getFullYear(), anchorDate.getMonth(), 1),
      end: new Date(anchorDate.getFullYear(), anchorDate.getMonth() + 1, 0),
    };
  }

  function formatShortDate(value) {
    return value.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
  }

  function updateUrl() {
    const query = new URLSearchParams(window.location.search);
    query.set("view", view);
    query.set("date", formatDate(anchorDate));
    window.history.replaceState({}, "", `${window.location.pathname}?${query}`);
  }

  function updateHeader() {
    const monthLabel = anchorDate.toLocaleDateString("fr-FR", {
      month: "long",
      year: "numeric",
    });
    periodLabel.textContent = monthLabel.charAt(0).toUpperCase() + monthLabel.slice(1);
    updateUrl();
  }

  function filterParameters() {
    return {
      search: searchInput.value.trim(),
      project: filters[0].value,
      assignee: filters[1].value,
      priority: filters[2].value,
      status: filters[3].value,
    };
  }

  async function loadCalendar() {
    const range = currentRange();
    updateHeader();
    loading.hidden = false;
    const query = new URLSearchParams({
      view,
      start: formatDate(range.start),
      end: formatDate(range.end),
      ...filterParameters(),
    });
    try {
      const response = await fetch(`${apiUrl}?${query}`, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Impossible de charger le calendrier.");
      lastPayload = payload;
      renderStatistics(payload.statistics);
      renderMonth(payload.tasks, range);
    } catch (error) {
      content.innerHTML = `<p class="calendar-empty">${escapeHtml(error.message)}</p>`;
    } finally {
      loading.hidden = true;
    }
  }

  function renderStatistics(statistics) {
    Object.entries(statistics).forEach(([name, value]) => {
      const target = root.querySelector(`[data-stat="${name}"]`);
      if (target) target.textContent = value;
    });
  }

  function groupTasks(tasks) {
    const grouped = new Map();
    tasks.forEach((task) => {
      const key = task.start.slice(0, 10);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(task);
    });
    return grouped;
  }

  function taskCard(task) {
    const date = new Date(task.start);
    const timeLabel = task.is_all_day
      ? "Toute la journée"
      : date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    const assignee = task.assignee
      ? `${escapeHtml(task.assignee.initials)} · ${escapeHtml(task.assignee.name)}`
      : "Non assigné";
    const project = task.project ? ` · ${escapeHtml(task.project.name)}` : "";
    return `
      <a href="${escapeHtml(task.detail_url)}"
         class="calendar-task-card event-${task.event_type} priority-${task.priority.toLowerCase()}"
         title="${escapeHtml(task.title)}">
        <small>${escapeHtml(task.event_label)} · ${escapeHtml(task.priority_label)} · ${timeLabel}</small>
        <strong>${escapeHtml(task.title)}</strong>
        <span>${assignee}${project}${task.attachment_count ? ` · ${task.attachment_count} fichier(s)` : ""}</span>
      </a>
    `;
  }

  function renderMonth(tasks, range) {
    const grouped = groupTasks(tasks);
    const firstCell = startOfWeek(range.start);
    const today = startOfDay(new Date());
    const weekdays = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
    const cells = Array.from({ length: 42 }, (_, index) => {
      const day = addDays(firstCell, index);
      const items = grouped.get(formatDate(day)) || [];
      const visible = items.slice(0, 3).map((task) => taskCard(task)).join("");
      const extra = items.length > 3
        ? `<button type="button" class="calendar-more" data-more-date="${formatDate(day)}">+ ${items.length - 3} autres</button>`
        : "";
      return `
        <div class="calendar-month-day ${day.getMonth() !== anchorDate.getMonth() ? "is-outside" : ""} ${sameDay(day, today) ? "is-today" : ""}"
             data-month-date="${formatDate(day)}">
          <span class="calendar-month-number">${day.getDate()}</span>
          ${visible}${extra}
        </div>
      `;
    }).join("");
    content.innerHTML = `
      <div class="calendar-month">
        ${weekdays.map((day) => `<div class="calendar-month-weekday">${day}</div>`).join("")}
        ${cells}
      </div>
    `;
  }

  function openModal(title, items) {
    modalTitle.textContent = title;
    modalList.innerHTML = items.length
      ? items.map((task) => `
          <a href="${escapeHtml(task.detail_url)}" class="calendar-modal-item">
            <strong>${escapeHtml(task.title)}</strong>
            <small>${escapeHtml(task.event_label ? `${task.event_label} · ${task.priority_label}` : task.priority_label || task.status_label || "")}</small>
          </a>
        `).join("")
      : '<p class="calendar-empty">Aucune tâche.</p>';
    modal.hidden = false;
    modalBackdrop.hidden = false;
  }

  function closeModal() {
    modal.hidden = true;
    modalBackdrop.hidden = true;
  }

  function createAt(date, hour, minute) {
    if (!canCreate) return;
    const deadline = new Date(date);
    deadline.setHours(hour, minute, 0, 0);
    const deadlineValue = `${formatDate(deadline)}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
    const next = `${window.location.pathname}${window.location.search}`;
    window.location.href = `${createUrl}?deadline=${encodeURIComponent(deadlineValue)}&next=${encodeURIComponent(next)}`;
  }

  document.getElementById("calendar-previous").addEventListener("click", () => {
    anchorDate = new Date(anchorDate.getFullYear(), anchorDate.getMonth() - 1, 1);
    loadCalendar();
  });

  document.getElementById("calendar-next").addEventListener("click", () => {
    anchorDate = new Date(anchorDate.getFullYear(), anchorDate.getMonth() + 1, 1);
    loadCalendar();
  });

  const todayButton = document.getElementById("calendar-today");
  if (todayButton) {
    todayButton.addEventListener("click", () => {
      anchorDate = startOfDay(new Date());
      loadCalendar();
    });
  }

  searchInput.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(loadCalendar, 300);
  });
  filters.forEach((filter) => filter.addEventListener("change", loadCalendar));

  content.addEventListener("click", (event) => {
    const more = event.target.closest("[data-more-date]");
    if (more && lastPayload) {
      event.preventDefault();
      const date = more.dataset.moreDate;
      const items = lastPayload.tasks.filter((task) => task.start.slice(0, 10) === date);
      openModal(formatShortDate(parseDate(date)), items);
      return;
    }
    if (event.target.closest(".calendar-task-card")) return;

    const monthCell = event.target.closest("[data-month-date]");
    if (monthCell) createAt(parseDate(monthCell.dataset.monthDate), 9, 0);
  });

  document.getElementById("calendar-undated").addEventListener("click", () => {
    if (lastPayload) openModal("Tâches sans date limite", lastPayload.without_due_tasks);
  });
  document.getElementById("calendar-modal-close").addEventListener("click", closeModal);
  modalBackdrop.addEventListener("click", closeModal);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });

  loadCalendar();
})();
