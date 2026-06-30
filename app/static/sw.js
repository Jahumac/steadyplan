/**
 * SteadyPlan — Service Worker
 *
 * Strategy:
 *  - App shell (CSS, JS, icons): Cache-first with background revalidation
 *  - Public/safe pages: Network-first with offline fallback
 *  - Authenticated financial pages: network-only with offline fallback
 *  - API-style JSON calls: network-only, never cached
 *
 * Cache name carries a version suffix — bump it on every deploy so old
 * caches get cleaned up by the activate handler and clients pick up new
 * CSS/JS instead of running stale shell assets indefinitely.
 */

const CACHE_NAME = 'steadyplan-cache-v2';

/* App shell files to pre-cache on install */
const APP_SHELL = [
  '/static/css/styles.css',
  '/static/js/charts.js',
  '/static/manifest.json',
  '/static/icons/icon-180.png',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

/* ── Install: pre-cache the app shell ─────────────────────────────────── */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(APP_SHELL).then(async () => {
        try {
          const resp = await fetch('/offline', { cache: 'reload' });
          if (resp.ok) await cache.put('/offline', resp);
        } catch (e) {}
      });
    })
  );
  self.skipWaiting();
});

/* ── Activate: clean up old caches ────────────────────────────────────── */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

/* ── Fetch: route requests through appropriate strategy ───────────────── */
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  /* Only handle same-origin GET requests */
  if (request.method !== 'GET' || url.origin !== self.location.origin) {
    return;
  }

  const safeNavPaths = new Set(['/login', '/setup', '/demo', '/offline']);

  /* Static assets: cache-first */
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirstStatic(request));
    return;
  }

  /* Page navigations: network-first with offline fallback */
  if (request.mode === 'navigate') {
    event.respondWith(safeNavPaths.has(url.pathname) ? networkFirstPage(request) : networkOnlyPage(request));
    return;
  }

  /* API-style JSON calls: never cached */
  if (url.pathname.includes('/api/') || request.headers.get('Accept')?.includes('application/json')) {
    event.respondWith(networkOnlyAPI(request));
    return;
  }

  /* Everything else: never cached */
  event.respondWith(networkOnlyPage(request));
});

/* ── Strategies ───────────────────────────────────────────────────────── */

function _staticCacheKey(request) {
  const url = new URL(request.url);
  url.search = '';
  return new Request(url.toString(), { method: 'GET' });
}

async function cacheFirstStatic(request) {
  const key = _staticCacheKey(request);
  const cached = await caches.match(key);
  if (cached) {
    /* Revalidate in background */
    fetch(request)
      .then((response) => {
        if (response.ok) {
          caches.open(CACHE_NAME).then((cache) => cache.put(key, response));
        }
      })
      .catch(() => {});
    return cached;
  }
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(CACHE_NAME);
    cache.put(key, response.clone());
  }
  return response;
}

async function networkFirstPage(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (e) {
    const cached = await caches.match(request);
    if (cached) return cached;

    return await offlinePage();
  }
}

async function networkOnlyPage(request) {
  try {
    return await fetch(request);
  } catch (e) {
    return await offlinePage();
  }
}

async function networkOnlyAPI(request) {
  try {
    return await fetch(request);
  } catch (e) {
    return new Response(JSON.stringify({ error: 'Offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

async function offlinePage() {
  const cached = await caches.match('/offline');
  if (cached) return cached;
  return new Response(offlineHTML(), {
    status: 503,
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  });
}

/* ── Offline fallback HTML ────────────────────────────────────────────── */
function offlineHTML() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#0f172a">
  <title>Offline · SteadyPlan</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: Inter, system-ui, -apple-system, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 2rem;
    }
    .offline-card { max-width: 400px; }
    .offline-icon { font-size: 3rem; margin-bottom: 1rem; opacity: 0.6; }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; color: #38bdf8; }
    p { color: #94a3b8; line-height: 1.6; margin-bottom: 1.5rem; }
    button {
      background: #38bdf8; color: #0f172a; border: none;
      padding: 0.75rem 2rem; border-radius: 999px;
      font-size: 0.95rem; font-weight: 600; cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="offline-card">
    <div class="offline-icon">🐢</div>
    <h1>You're offline</h1>
    <p>For privacy, SteadyPlan doesn't store your financial pages for offline viewing. Connect to the internet to access your dashboard.</p>
    <p style="margin-top:0.5rem;font-size:0.9rem;">
      <a href="https://github.com/Jahumac/steadyplan" rel="noopener noreferrer" target="_blank" style="color:#38bdf8;">github.com/Jahumac/steadyplan</a>
    </p>
    <button onclick="location.reload()">Try Again</button>
  </div>
</body>
</html>`;
}
