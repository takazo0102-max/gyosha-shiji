// TaskFlow Service Worker
// Airtable-themed PWA — offline-first caching strategy

const CACHE = 'taskflow-v4';

// Core app shell
const STATIC = [
  './',
  './index.html',
  './icon.svg',
  './manifest.json',
];

// CDN resources to cache on first fetch
const CDN_PATTERNS = [
  'unpkg.com',
  'cdn.tailwindcss.com',
  'fonts.googleapis.com',
  'fonts.gstatic.com',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  // Skip non-GET and chrome-extension
  if (request.method !== 'GET' || url.protocol === 'chrome-extension:') return;

  // API calls (JSONBin, Gemini) — network-only
  if (url.host.includes('jsonbin.io') || url.host.includes('googleapis.com') && url.pathname.includes('generateContent')) {
    return;
  }

  // CDN resources — cache-first
  if (CDN_PATTERNS.some(p => url.href.includes(p))) {
    e.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE).then(c => c.put(request, clone));
          }
          return res;
        }).catch(() => cached);
      })
    );
    return;
  }

  // App shell — network-first with cache fallback
  e.respondWith(
    fetch(request)
      .then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(request, clone));
        }
        return res;
      })
      .catch(() => caches.match(request).then(c => c || caches.match('./index.html')))
  );
});
