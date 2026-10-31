/* SteadyPlan — PWA wiring: service worker registration + install prompt.
 *
 * Lives in its own file (not app.js) so the login page can use it too. The login
 * page is a standalone template that never loads app.js, so without this Chrome
 * would not offer to install the app until after the first sign-in.
 *
 * Registered on every page that includes it; harmless when the page has no
 * #pwa-install-btn (e.g. the login screen, which relies on the browser's own
 * install affordance).
 */
(function () {
  'use strict';

  /* ── Service worker ──────────────────────────────────────────────────── */
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js')
      .then(reg => { setInterval(() => reg.update(), 60 * 60 * 1000); })
      .catch(() => { });
  }

  /* ── Install prompt ────────────────────────────────────────────────────
     Chrome/Edge fire `beforeinstallprompt` once the app is installable. We
     intercept it and show our own button instead of relying on the browser's
     mini-infobar, then replay the held event on click. Stays hidden when the
     app is already installed or already running standalone. */
  var deferredInstallPrompt = null;
  var pwaInstallBtn = document.getElementById('pwa-install-btn');

  function pwaIsStandalone() {
    return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
           window.navigator.standalone === true;
  }

  function pwaHideInstallButton() {
    if (pwaInstallBtn) { pwaInstallBtn.classList.add('hidden'); }
  }

  window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();
    deferredInstallPrompt = event;
    if (pwaInstallBtn && !pwaIsStandalone()) {
      pwaInstallBtn.classList.remove('hidden');
    }
  });

  if (pwaInstallBtn) {
    if (pwaIsStandalone()) { pwaHideInstallButton(); }
    pwaInstallBtn.addEventListener('click', function () {
      if (!deferredInstallPrompt) { return; }
      deferredInstallPrompt.prompt();
      deferredInstallPrompt.userChoice.then(function () {
        deferredInstallPrompt = null;
        pwaHideInstallButton();
      }).catch(function () {
        deferredInstallPrompt = null;
        pwaHideInstallButton();
      });
    });
  }

  window.addEventListener('appinstalled', function () {
    deferredInstallPrompt = null;
    pwaHideInstallButton();
  });
})();
