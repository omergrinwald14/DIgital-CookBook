// Minimal service worker — required for PWA install + Web Share Target.
// No caching yet; the fetch handler just lets the network handle everything.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {
  // Pass-through (its mere presence satisfies the install criteria).
});
