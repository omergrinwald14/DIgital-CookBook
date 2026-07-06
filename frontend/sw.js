// Service worker — PWA install + Web Share Target + Background Sync retries.
importScripts("share-queue.js");

const API_BASE = "https://digital-cookbook-api.onrender.com"; // matches app.js

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
// Web Share Target: intercept the share navigation, queue the link, and
// answer 204 No Content. A 204 aborts the navigation, so our window never
// opens and the user stays in Instagram/TikTok. Anything less than the
// happy path falls through to share.html (the visible fallback page).
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isShare =
    url.origin === self.location.origin &&
    (url.pathname === "/share.html" || url.pathname === "/share");
  if (!isShare || event.request.mode !== "navigate") return;
  event.respondWith(handleShare(event.request));
});

async function handleShare(request) {
  try {
    const params = new URL(request.url).searchParams;
    const raw = `${params.get("url") || ""} ${params.get("text") || ""}`;
    const link = (raw.match(/https?:\/\/\S+/i) || [])[0];
    // No link, or no Background Sync to guarantee delivery → visible page.
    if (!link || !("sync" in self.registration)) return fetch(request);
    await enqueueShare(link);
    await self.registration.sync.register("share-import");
    return new Response(null, { status: 204 }); // stay in the sharing app
  } catch {
    return fetch(request); // any hiccup: fall back to share.html
  }
}

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
