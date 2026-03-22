// AI Fitness Coach v1 — Service Worker (offline caching)
const CACHE_NAME = 'coach-v1';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/css/styles.css',
    '/js/app.js',
    '/js/api.js',
    '/js/router.js',
    '/js/components/dashboard.js',
    '/js/components/workout.js',
    '/js/components/meals.js',
    '/js/components/shopping.js',
    '/js/components/progress.js',
    '/manifest.json',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    if (event.request.url.includes('/api/')) {
        // Network-first for API calls
        event.respondWith(
            fetch(event.request).catch(() => caches.match(event.request))
        );
    } else {
        // Cache-first for static assets
        event.respondWith(
            caches.match(event.request).then((r) => r || fetch(event.request))
        );
    }
});
