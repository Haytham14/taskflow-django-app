document.addEventListener("DOMContentLoaded", function () {
  const board = document.getElementById("board");
  if (!board) return;

  function getCsrfToken(form) {
    const input = form.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : "";
  }

  function updateColumnCounts() {
    document.querySelectorAll(".board-column").forEach(function (column) {
      const zone = column.querySelector(".card-drop-zone");
      const count = zone.querySelectorAll(".task-card").length;
      column.querySelector(".count-pill").textContent = count;

      const emptyMsg = zone.querySelector(".empty-column");
      if (count > 0 && emptyMsg) {
        emptyMsg.remove();
      }
      if (count === 0 && !zone.querySelector(".empty-column")) {
        const p = document.createElement("p");
        p.className = "empty-column";
        p.textContent = "Aucune tâche ici.";
        zone.appendChild(p);
      }
    });
  }

  function moveCard(card, targetZone) {
    const emptyMsg = targetZone.querySelector(".empty-column");
    if (emptyMsg) emptyMsg.remove();
    targetZone.appendChild(card);
    updateColumnCounts();
  }

  function requiresConfirmation(oldStatus, newStatus) {
    return (
      oldStatus !== newStatus &&
      (newStatus === "TO_VERIFY" ||
        newStatus === "DONE" ||
        oldStatus === "DONE" ||
        oldStatus === "TO_VERIFY")
    );
  }

  function openConfirmationPage(card, newStatus) {
    const nextUrl = window.location.pathname + window.location.search;
    const params = new URLSearchParams({ status: newStatus, next: nextUrl });
    window.location.href =
      "/tasks/" + card.dataset.taskId + "/status/confirm/?" + params.toString();
  }

  async function updateStatus(taskId, status, csrfToken) {
    const url = "/tasks/" + taskId + "/status/";
    const body = new URLSearchParams({ status: status });
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrfToken,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    });
    if (!response.ok) {
      const data = await response.json().catch(function () {
        return {};
      });
      throw new Error(data.error || "Impossible de mettre à jour cette tâche.");
    }
    return response.json();
  }

  // Progressive enhancement: the <select> + hidden submit button work with
  // no JavaScript at all (full page reload). With JS, changing the select
  // updates the card instantly and hides the fallback button.
  document.querySelectorAll(".status-form").forEach(function (form) {
    form.classList.add("js-enhanced");
    const select = form.querySelector(".status-select");
    const card = form.closest(".task-card");

    select.addEventListener("change", function () {
      const oldStatus = card.dataset.status;
      const newStatus = select.value;

      if (requiresConfirmation(oldStatus, newStatus)) {
        openConfirmationPage(card, newStatus);
        return;
      }

      const csrfToken = getCsrfToken(form);
      updateStatus(card.dataset.taskId, newStatus, csrfToken)
        .then(function () {
          card.dataset.status = newStatus;
          const targetZone = document.querySelector('.card-drop-zone[data-status="' + newStatus + '"]');
          if (targetZone) moveCard(card, targetZone);
        })
        .catch(function (err) {
          select.value = oldStatus;
          alert(err.message);
        });
    });
  });

  // Native HTML5 drag and drop between columns.
  let draggedCard = null;
  let suppressNextClick = false;

  board.querySelectorAll(".task-card[draggable='true']").forEach(function (card) {
    card.addEventListener("dragstart", function () {
      draggedCard = card;
      suppressNextClick = true;
      card.classList.add("dragging");
    });
    card.addEventListener("dragend", function () {
      card.classList.remove("dragging");
      draggedCard = null;
    });
  });

  board.querySelectorAll(".card-drop-zone").forEach(function (zone) {
    zone.addEventListener("dragover", function (event) {
      event.preventDefault();
      zone.classList.add("drop-hover");
    });
    zone.addEventListener("dragleave", function () {
      zone.classList.remove("drop-hover");
    });
    zone.addEventListener("drop", function (event) {
      event.preventDefault();
      zone.classList.remove("drop-hover");
      if (!draggedCard) return;

      // Snapshot the card now. The native "dragend" event fires right after
      // "drop" and resets the shared `draggedCard` tracker to null — if we
      // read `draggedCard` again later inside the fetch's .then(), it may
      // already be null by the time the network response arrives.
      const card = draggedCard;
      const oldStatus = card.dataset.status;
      const newStatus = zone.dataset.status;
      const form = card.querySelector(".status-form");

      if (!form) return; // this user isn't allowed to move this card
      if (oldStatus === newStatus) return;

      if (requiresConfirmation(oldStatus, newStatus)) {
        openConfirmationPage(card, newStatus);
        return;
      }

      const csrfToken = getCsrfToken(form);

      updateStatus(card.dataset.taskId, newStatus, csrfToken)
        .then(function () {
          card.dataset.status = newStatus;
          const select = card.querySelector(".status-select");
          if (select) select.value = newStatus;
          moveCard(card, zone);
        })
        .catch(function (err) {
          alert(err.message);
        });
    });
  });

  // Make the whole card clickable, not just the title link. Clicks that land
  // on an interactive element inside the card (the title link itself, the
  // Edit/Delete links, or the status form) are left alone so those keep
  // working exactly as before.
  board.querySelectorAll(".task-card[data-href]").forEach(function (card) {
    card.addEventListener("click", function (event) {
      if (suppressNextClick) {
        suppressNextClick = false;
        return;
      }
      if (event.target.closest("a, button, select, option, label, input")) {
        return;
      }
      window.location.href = card.dataset.href;
    });
  });
});
