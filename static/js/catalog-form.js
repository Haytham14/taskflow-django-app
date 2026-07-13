document.addEventListener("DOMContentLoaded", () => {
  const createRow = (list) => {
    const row = document.createElement("div");
    row.className = "catalog-habilitation-field";
    row.dataset.dynamicRow = "";
    const inputName = list.dataset.inputName;
    const placeholder = list.dataset.placeholder;
    row.innerHTML = `
      <input type="text" name="${inputName}" class="input" placeholder="${placeholder}" required>
      <button type="button" class="icon-button catalog-remove-item" data-remove-item aria-label="Supprimer cette ligne" title="Supprimer">&times;</button>
    `;
    return row;
  };

  document.querySelectorAll("[data-add-to]").forEach((button) => {
    button.addEventListener("click", () => {
      const list = document.getElementById(button.dataset.addTo);
      if (!list) return;
      const row = createRow(list);
      list.appendChild(row);
      row.querySelector("input").focus();
    });
  });

  document.querySelectorAll("[data-dynamic-list]").forEach((list) => {
    list.addEventListener("click", (event) => {
      const removeButton = event.target.closest("[data-remove-item]");
      if (!removeButton) return;

      const rows = list.querySelectorAll("[data-dynamic-row]");
      if (rows.length === 1) {
        const input = rows[0].querySelector("input");
        input.value = "";
        input.focus();
        return;
      }
      removeButton.closest("[data-dynamic-row]").remove();
    });
  });
});
