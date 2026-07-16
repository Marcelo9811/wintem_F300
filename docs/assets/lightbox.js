(() => {
  const lightbox = document.querySelector("#image-lightbox");
  const expandedImage = lightbox?.querySelector("img");
  const closeButton = lightbox?.querySelector(".lightbox-close");
  let opener = null;

  if (!lightbox || !expandedImage || !closeButton) return;

  const close = () => {
    lightbox.hidden = true;
    expandedImage.src = "";
    expandedImage.alt = "";
    document.body.classList.remove("lightbox-open");
    opener?.focus();
  };

  document.querySelectorAll("[data-lightbox-src]").forEach((button) => {
    button.addEventListener("click", () => {
      opener = button;
      expandedImage.src = button.dataset.lightboxSrc;
      expandedImage.alt = button.dataset.lightboxAlt || "Figura ampliada";
      lightbox.hidden = false;
      document.body.classList.add("lightbox-open");
      closeButton.focus();
    });
  });

  closeButton.addEventListener("click", close);
  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !lightbox.hidden) close();
  });
})();
