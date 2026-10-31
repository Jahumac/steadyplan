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
  /* The script URL carries a ?v=<mtime> cache-buster supplied by the template.
     This matters behind a CDN: Cloudflare caches .js by default and was serving
     a day-old /sw.js, so a deployed service-worker update could never reach
     clients. A per-build URL gives it a fresh cache key every time. */
  var pwaInit = document.getElementById('pwa-init');
  var swUrl = (pwaInit && pwaInit.getAttribute('data-sw-url')) || '/sw.js';

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register(swUrl)
      .then(reg => { setInterval(() => reg.update(), 60 * 60 * 1000); })
      .catch(() => { });

    /* One-off cleanup: an earlier build registered the worker from /static/sw.js,
       which scopes it to /static/ only, so it could serve stale assets from under
       /static/ without ever controlling a page. Drop any such registration. */
    navigator.serviceWorker.getRegistrations().then(function (regs) {
      regs.forEach(function (reg) {
        var script = (reg.active && reg.active.scriptURL) || '';
        if (reg.scope && reg.scope.indexOf('/static/') !== -1 && script.indexOf('/static/sw.js') !== -1) {
          reg.unregister();
        }
      });
    }).catch(function () { });
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
