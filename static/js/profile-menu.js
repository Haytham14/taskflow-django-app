document.addEventListener("DOMContentLoaded", function () {
  const menu = document.querySelector(".topbar-profile");
  if (!menu) return;

  document.addEventListener("pointerdown", function (event) {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") menu.open = false;
  });
});
