// Service worker: makes the app installable and lets it open without a network.
//
// Only the app itself is cached (its page, scripts, styles and icons). Nothing
// under /api is ever cached: tasks, images and progress always come from the
// server, and need a login.

const CACHE = 'levet-shell-v1'
const SHELL = ['/', '/manifest.webmanifest', '/favicon.svg']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((name) => name !== CACHE).map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/')) return

  if (url.pathname.startsWith('/assets/')) {
    // Built files carry a hash of their content in the name, so a cached copy is never stale.
    event.respondWith(cacheFirst(request))
  } else if (request.mode === 'navigate') {
    // Any page of the app is the same document; take the newest, fall back to the stored one.
    event.respondWith(networkFirst(request, '/'))
  } else {
    event.respondWith(networkFirst(request, request))
  }
})

async function cacheFirst(request) {
  const cache = await caches.open(CACHE)
  const cached = await cache.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) cache.put(request, response.clone())
  return response
}

async function networkFirst(request, cacheKey) {
  const cache = await caches.open(CACHE)
  try {
    const response = await fetch(request)
    if (response.ok) cache.put(cacheKey, response.clone())
    return response
  } catch (error) {
    const cached = await cache.match(cacheKey)
    if (cached) return cached
    throw error
  }
}
