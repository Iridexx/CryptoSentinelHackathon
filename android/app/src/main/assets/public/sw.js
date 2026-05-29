const CACHE_NAME = 'cryptowatch-v1';
const APP_SHELL = [
  '/',
  '/index.html',
  '/manifest.json',
];

// Installa e mette in cache l'app shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

// Rimuove le vecchie cache
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Strategia cache-first per l'app shell, network-first per le API
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.hostname === 'api.coingecko.com') {
    event.respondWith(
      fetch(event.request).catch(() => new Response('{"error":"offline"}', { headers: { 'Content-Type': 'application/json' } }))
    );
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request).catch(() => caches.match('/index.html')))
  );
});

// Riceve messaggi dal main thread con i dati degli allarmi scattati
self.addEventListener('message', (event) => {
  if (event.data?.type === 'PRICE_ALERT') {
    const { coinName, direction, threshold, currentPrice } = event.data;
    const symbol = direction === 'above' ? '▲' : '▼';
    const dirLabel = direction === 'above' ? 'superato' : 'sceso sotto';
    self.registration.showNotification(`${symbol} Allarme ${coinName}`, {
      body: `${coinName} ha ${dirLabel} $${threshold.toLocaleString('it-IT')} — Prezzo attuale: $${currentPrice.toLocaleString('it-IT')}`,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      tag: `alert-${coinName}-${direction}-${threshold}`,
      renotify: true,
      requireInteraction: false,
      silent: false,
      data: { url: '/' },
    });
  }
});

// Click sulla notifica apre l'app
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      const existing = clients.find((c) => c.url.includes(self.location.origin));
      if (existing) return existing.focus();
      return self.clients.openWindow('/');
    })
  );
});
