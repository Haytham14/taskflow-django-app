document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".file-field").forEach(function (field) {
    const input = field.querySelector('input[type="file"]');
    const nameEl = field.querySelector(".file-field-name");
    if (!input || !nameEl) return;

    const placeholder = nameEl.dataset.placeholder || "Aucun fichier sélectionné";

    input.addEventListener("change", function () {
      if (input.files && input.files.length === 1) {
        nameEl.textContent = input.files[0].name;
      } else if (input.files && input.files.length > 1) {
        nameEl.textContent = input.files.length + " fichiers sélectionnés";
      } else {
        nameEl.textContent = placeholder;
      }
    });
  });
});
