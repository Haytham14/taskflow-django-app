document.addEventListener("DOMContentLoaded", () => {
  const textarea = document.querySelector(".task-comments-panel .comment-form textarea");
  if (!textarea) return;

  const resize = () => {
    textarea.style.height = "42px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 96)}px`;
  };

  textarea.addEventListener("input", resize);
  resize();
});
