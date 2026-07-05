// Service worker — PWA install + Web Share Target + Background Sync retries.
importScripts("share-queue.js");

const API_BASE = "https://digital-cookbook-api.onrender.com"; // matches app.js

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {
  // Pass-through (its mere presence satisfies the install criteria).
});

// Fires when the browser decides we're online — even if the share page is
// long closed. waitUntil keeps the SW alive until the queue is drained.
self.addEventListener("sync", (event) => {
  if (event.tag === "share-import") {
    event.waitUntil(drainShareQueue());
  }
});

async function drainShareQueue() {
  for (const share of await listShares()) {
    const res = await fetch(`${API_BASE}/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: share.url }),
    });
    // 4xx = bad URL, retrying can't fix it — drop the entry.
    // ok = saved (idempotent, so a re-run is harmless) — drop it too.
    // 5xx = transient server trouble — throw; the browser re-syncs later.
    if (res.ok || (res.status >= 400 && res.status < 500)) {
      await removeShare(share.id);
    } else {
      throw new Error(`import failed: HTTP ${res.status}`);
    }
  }
  // A network error (fetch rejects) also throws out of here — same retry path.
}
