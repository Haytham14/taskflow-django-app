document.addEventListener("DOMContentLoaded", function () {
  const MONTH_NAMES = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
  ];
  const WEEKDAY_LABELS = ["Lu", "Ma", "Me", "Je", "Ve", "Sa", "Di"];

  function parseISODate(iso) {
    // Parsing "YYYY-MM-DD" via components (not `new Date(iso)`) avoids the
    // classic off-by-one-day bug caused by ISO strings being read as UTC.
    if (!iso) return null;
    const parts = iso.split("-");
    if (parts.length !== 3) return null;
    const year = parseInt(parts[0], 10);
    const month = parseInt(parts[1], 10) - 1;
    const day = parseInt(parts[2], 10);
    if (Number.isNaN(year) || Number.isNaN(month) || Number.isNaN(day)) return null;
    return new Date(year, month, day);
  }

  function formatISODate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function formatDisplayDate(date) {
    const d = String(date.getDate()).padStart(2, "0");
    const m = String(date.getMonth() + 1).padStart(2, "0");
    return `${d}/${m}/${date.getFullYear()}`;
  }

  function sameDay(a, b) {
    return (
      !!a && !!b &&
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate()
    );
  }

  function setUpPicker(form) {
    const nativeGroup = form.querySelector(".date-range-native");
    const startInput = form.querySelector(".range-start-input");
    const endInput = form.querySelector(".range-end-input");
    if (!nativeGroup || !startInput || !endInput) return;

    // Committed = what's actually been applied (mirrors the real inputs).
    // Selecting = the in-progress choice while the popover is open.
    let committedStart = parseISODate(startInput.value) || new Date();
    let committedEnd = parseISODate(endInput.value) || committedStart;
    let selectingStart = committedStart;
    let selectingEnd = committedEnd;
    let viewDate = new Date(committedStart.getFullYear(), committedStart.getMonth(), 1);

    const picker = document.createElement("div");
    picker.className = "date-range-picker";

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "date-range-trigger";
    trigger.innerHTML = '<svg class="ui-icon" aria-hidden="true"><use href="#nav-icon-calendar"></use></svg> <span class="date-range-trigger-text"></span>';
    picker.appendChild(trigger);

    const popover = document.createElement("div");
    popover.className = "date-range-popover";
    popover.hidden = true;
    popover.innerHTML = `
      <div class="calendar-header">
        <button type="button" class="calendar-nav calendar-prev" aria-label="Mois précédent"><svg class="ui-icon" aria-hidden="true"><use href="#nav-icon-chevron-left"></use></svg></button>
        <span class="calendar-month-year"></span>
        <button type="button" class="calendar-nav calendar-next" aria-label="Mois suivant"><svg class="ui-icon" aria-hidden="true"><use href="#nav-icon-chevron-right"></use></svg></button>
      </div>
      <div class="calendar-weekdays">
        ${WEEKDAY_LABELS.map((label) => `<span>${label}</span>`).join("")}
      </div>
      <div class="calendar-grid"></div>
      <div class="calendar-footer">
        <button type="button" class="btn btn-ghost calendar-cancel">Annuler</button>
        <button type="submit" class="btn btn-primary calendar-apply">Appliquer</button>
      </div>
    `;
    picker.appendChild(popover);

    nativeGroup.insertAdjacentElement("beforebegin", picker);
    nativeGroup.classList.add("js-picker-hidden");
    const triggerText = trigger.querySelector(".date-range-trigger-text");
    const monthYearLabel = popover.querySelector(".calendar-month-year");
    const grid = popover.querySelector(".calendar-grid");

    function updateTriggerLabel() {
      triggerText.textContent =
        formatDisplayDate(committedStart) + " \u2192 " + formatDisplayDate(committedEnd);
    }

    function updatePendingRangeLabel() {
      triggerText.textContent = formatDisplayDate(selectingStart) + " \u2192 choisir une date de fin";
    }

    function commitSelection() {
      if (!selectingStart) return;

      const finalStart = selectingEnd && selectingStart > selectingEnd ? selectingEnd : selectingStart;
      const finalEnd = selectingEnd
        ? (selectingStart > selectingEnd ? selectingStart : selectingEnd)
        : selectingStart;

      committedStart = finalStart;
      committedEnd = finalEnd;
      startInput.value = formatISODate(finalStart);
      endInput.value = formatISODate(finalEnd);
      updateTriggerLabel();
    }

    function renderCalendar() {
      monthYearLabel.textContent = MONTH_NAMES[viewDate.getMonth()] + " " + viewDate.getFullYear();
      grid.innerHTML = "";

      const year = viewDate.getFullYear();
      const month = viewDate.getMonth();
      const firstOfMonth = new Date(year, month, 1);
      // JS getDay(): 0=Sun..6=Sat. Shift so 0=Mon..6=Sun (French week start).
      const firstWeekdayMonFirst = (firstOfMonth.getDay() + 6) % 7;
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      const daysInPrevMonth = new Date(year, month, 0).getDate();
      const today = new Date();

      const rangeStart = selectingStart && selectingEnd && selectingStart > selectingEnd ? selectingEnd : selectingStart;
      const rangeEnd = selectingStart && selectingEnd && selectingStart > selectingEnd ? selectingStart : selectingEnd;

      for (let i = 0; i < 42; i++) {
        const dayOffset = i - firstWeekdayMonFirst + 1;
        let cellDate;
        let otherMonth = false;

        if (dayOffset < 1) {
          cellDate = new Date(year, month - 1, daysInPrevMonth + dayOffset);
          otherMonth = true;
        } else if (dayOffset > daysInMonth) {
          cellDate = new Date(year, month + 1, dayOffset - daysInMonth);
          otherMonth = true;
        } else {
          cellDate = new Date(year, month, dayOffset);
        }

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "calendar-day";
        btn.textContent = cellDate.getDate();

        if (otherMonth) btn.classList.add("calendar-day-muted");
        if (sameDay(cellDate, today)) btn.classList.add("calendar-day-today");
        if (rangeStart && sameDay(cellDate, rangeStart)) btn.classList.add("calendar-day-start");
        if (rangeEnd && sameDay(cellDate, rangeEnd)) btn.classList.add("calendar-day-end");
        if (rangeStart && rangeEnd && cellDate > rangeStart && cellDate < rangeEnd) {
          btn.classList.add("calendar-day-in-range");
        }

        btn.addEventListener("click", function (event) {
          event.stopPropagation();

          if (!selectingStart || (selectingStart && selectingEnd)) {
            selectingStart = cellDate;
            selectingEnd = null;
            committedStart = cellDate;
            committedEnd = cellDate;
            startInput.value = formatISODate(cellDate);
            endInput.value = formatISODate(cellDate);
            updatePendingRangeLabel();
          } else {
            selectingEnd = cellDate;
            commitSelection();
          }
          renderCalendar();
        });

        grid.appendChild(btn);
      }
    }

    function openPopover() {
      selectingStart = committedStart;
      selectingEnd = committedEnd;
      viewDate = new Date(committedStart.getFullYear(), committedStart.getMonth(), 1);
      renderCalendar();
      popover.hidden = false;
      trigger.classList.add("open");
    }

    function closePopover() {
      popover.hidden = true;
      trigger.classList.remove("open");
    }

    trigger.addEventListener("click", function () {
      if (popover.hidden) {
        openPopover();
      } else {
        closePopover();
      }
    });

    popover.querySelector(".calendar-prev").addEventListener("click", function () {
      viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth() - 1, 1);
      renderCalendar();
    });
    popover.querySelector(".calendar-next").addEventListener("click", function () {
      viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 1);
      renderCalendar();
    });
    popover.querySelector(".calendar-cancel").addEventListener("click", closePopover);

    popover.querySelector(".calendar-apply").addEventListener("click", function () {
      commitSelection();
      // No preventDefault: this button is type="submit" inside the same
      // form as the (now updated) hidden/native inputs, so the browser's
      // normal submit continues right after this handler runs.
    });

    document.addEventListener("click", function (event) {
      if (!picker.contains(event.target)) closePopover();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closePopover();
    });

    updateTriggerLabel();
  }

  document.querySelectorAll(".custom-range-form").forEach(setUpPicker);
});
