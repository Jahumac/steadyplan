(() => {
  const dialog = document.querySelector('.lightbox');
  if (!dialog) return;

  const image = dialog.querySelector('.lightbox-image');
  const title = dialog.querySelector('.lightbox-title');
  const caption = dialog.querySelector('.lightbox-caption');
  const closeButton = dialog.querySelector('.lightbox-close');
  const triggers = [...document.querySelectorAll('.screenshot-trigger')];
  let lastTrigger = null;

  const closeLightbox = () => {
    if (!dialog.open) return;
    dialog.close();
    if (lastTrigger) {
      lastTrigger.focus();
    }
  };

  triggers.forEach((trigger) => {
    trigger.addEventListener('click', (event) => {
      event.preventDefault();
      lastTrigger = trigger;
      image.src = trigger.href;
      image.alt = trigger.querySelector('img')?.alt || 'Full screenshot';
      title.textContent = trigger.dataset.lightboxTitle || 'Screenshot';
      caption.textContent = trigger.dataset.lightboxCaption || 'Full preview';
      dialog.showModal();
    });
  });

  closeButton?.addEventListener('click', closeLightbox);

  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) {
      closeLightbox();
    }
  });

  dialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    closeLightbox();
  });
})();
