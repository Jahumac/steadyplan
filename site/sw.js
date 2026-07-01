const CACHE_NAME = 'steadyplan-lite-v1';
const ASSETS = [
  './index.html',
  './sandbox.html',
  './manifest.json',
  './assets/site.css',
  './assets/brand/steadyplan-app-icon-1024.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS);
    })
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).catch(() => {
        if (event.request.mode === 'navigate') {
          return caches.match('./sandbox.html');
        }
      });
    })
  );
});
