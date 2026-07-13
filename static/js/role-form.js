document.addEventListener("DOMContentLoaded", function () {
  const editor = document.querySelector(".role-editor");
  if (!editor) return;

  function setChecked(container, checked) {
    container.querySelectorAll('input[name="permissions"]').forEach(function (input) {
      input.checked = checked;
    });
  }

  editor.querySelectorAll("[data-permissions-all]").forEach(function (button) {
    button.addEventListener("click", function () {
      setChecked(editor, button.dataset.permissionsAll === "on");
    });
  });

  editor.querySelectorAll(".permission-module").forEach(function (module) {
    const toggle = module.querySelector(".permission-module-toggle");
    toggle.addEventListener("click", function () {
      const inputs = Array.from(module.querySelectorAll('input[name="permissions"]'));
      const allChecked = inputs.length > 0 && inputs.every(function (input) { return input.checked; });
      inputs.forEach(function (input) { input.checked = !allChecked; });
      toggle.textContent = allChecked ? "Tout sélectionner" : "Tout retirer";
    });
  });
});
