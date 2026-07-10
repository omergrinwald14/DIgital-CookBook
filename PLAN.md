# Digital CookBook — Build Plan

> Living roadmap. We build in baby steps — one small, approved task at a time.

## Context
A free app that turns Instagram cooking videos into a browsable, categorized recipe
book. Daily use: see a reel → tap Share → app saves it, auto-sorted into a category,
with ingredients, quantities, steps, and a link back to the video. Later, open the app
and browse by category to cook.

- **Users:** owner + family/friends (shared data, light login). Not public.
- **Cost:** must stay on free tiers.
- **Stack:** Python backend (FastAPI) + JavaScript PWA frontend.

## Confirmed product decisions
- **Categories are a fixed list, created/managed by the user inside the app.** The LLM
  picks a category from that list — it cannot invent new ones.
- **Unreadable / no-caption posts** are still saved: ingredients, quantities, and steps
  are `null`, and the recipe goes into the **"Unknown"** category.
- **Low-confidence categorization** also falls back to **"Unknown"**.

## Architecture
```
Instagram URL (from Share / Shortcut / paste)
        │
        ▼
Python backend (FastAPI)
  1. Apify API     → fetch caption + thumbnail + video link
  2. Gemini (free) → caption + category list → {title, ingredients[], steps[], category}
  3. Supabase      → save recipe
        │
        ▼
JS PWA frontend → browse categories → view recipe → open original video
```

### Components & free tiers
| Layer | Tool | Notes |
|---|---|---|
| Backend API | Python 3 + FastAPI + uvicorn | core fetch + parse logic |
| Instagram fetch | Apify Instagram Scraper (hosted API) | free tier; handles login/cookies for us. **Proven working.** |
| Parse + categorize | Google Gemini API | free tier; picks category from fixed list |
| Database + auth | Supabase (Postgres) | shared data; magic-link / Google login |
| Frontend | PWA (HTML/CSS/JS) | installable; Web Share Target on Android |
| Hosting | Backend on Render/Fly; frontend on Cloudflare Pages/Vercel | all free |

### Data model (start simple)
Ingredients/steps stored as JSON columns on the recipe row for v1.
- **categories**: `id, name, created_at`
- **recipes**: `id, title, category_id (null → Unknown), source_url, thumbnail,
  ingredients (json, nullable), steps (json, nullable), is_favorite, is_up_next,
  added_by, created_at`

## Build phases
**Phase 1 — Walking skeleton (prove the risky core first): ✅ COMPLETE**
- [x] 1a. Backend folder structure + Python virtual environment + `.gitignore`.
- [x] 1b. Fetch function: Instagram URL → caption. **Proven working via Apify API.**
- [x] 1c. Gemini parser: caption + category list → structured JSON. **Proven (gemini-2.5-flash).**
- [x] 1d. FastAPI `POST /import` (URL → fetch → parse → recipe JSON). **Proven end-to-end.**

**Phase 2 — Storage (Supabase):**
- [x] 2a. Create Supabase project + store URL/secret key in `.env`.
- [x] 2b. Create `categories` + `recipes` tables (RLS enabled); seed categories.
- [x] 2c. `storage.py` `save_recipe()` — maps category name→id (Unknown→null).
- [x] 2d. Wire `save_recipe` into `POST /import`. **Proven: import now persists.**
- [x] 2e. Read endpoints: `GET /recipes` and `GET /categories` (feeds the frontend).

**Phase 3 — Frontend:** static frontend in `frontend/` (index.html, app.js,
styles.css), served over HTTP. **Read path + category management proven.** ✅ COMPLETE
- [x] 3a-1. Backend CORS (`CORSMiddleware`) so the browser frontend can call the API.
- [x] 3a-2. Frontend scaffold; fetch + render categories.
- [x] 3a-3a. Render recipes as cards (title, thumbnail, source-video link). **Bugfix:**
  reuse one Supabase client (singleton) — per-request `create_client()` stalled and
  wedged the server. First request warms up (~10-25s once), then ~0.2s.
- [x] 3a-3b. Category chips filter the recipe list (+ "All" chip, active highlight).
- [x] 3a-4. Click a card to expand its ingredients + steps.
- [x] 3a-5. In-app category management (first **write** feature beyond import):
  `POST /categories`, `DELETE /categories/{id}`; frontend UI to add/remove categories.
  **Backend proven via TestClient round-trip; Phase 3 complete.**

> Dev note: browser caches `app.js`/`styles.css` — hard-refresh (Ctrl+Shift+R) after edits.

**Phase 3.5 — user-requested extras: ✅ COMPLETE**
- [x] Web import: paste an Instagram URL in the app → `POST /import` (the Phase 4
  paste-link fallback, pulled forward).
- [x] Collections: **Favorites** + **Up Next** — cross-category, per-recipe flags
  (`is_favorite`, `is_up_next`). `PATCH /recipes/{id}`; filter chips + card toggles.
- [x] Recipe deletion: `DELETE /recipes/{id}` + a corner × on each recipe card.

**Phase 4 — Capture (write path):** Android Web Share Target; iOS Shortcut. (In-app
paste-link already works — see Phase 3.5.) All hit `POST /import`.
- [x] 4-1. Installable PWA: web app manifest + icon, linked in `index.html`.
- [x] 4-2. Minimal service worker (`sw.js`) — required for install + share target.
- [x] 4-3. Web Share Target: manifest `share_target` + `share.html` handler.
  **Proven end-to-end on a real Android phone** (share reel → recipe saved).
- [ ] 4-4. iOS Shortcut: POSTs the shared link to `/import`.
- [x] 4-5. Fire-and-forget share: queue shares in IndexedDB + Background Sync —
  instant confirmation, automatic retry. Decouples the user from Render's
  cold-start wait. **Proven on a real Android phone.** After saving, the share
  window closes itself (`window.close()`) so Android returns to Instagram.
- [x] **Deployed (permanent, free):** backend on **Render**
  (`https://digital-cookbook-api.onrender.com`), frontend on **Cloudflare
  Workers** (`https://digital-cookbook.omergrinwald14.workers.dev`). Config is
  version-controlled: `render.yaml` (backend) + `wrangler.jsonc` (frontend).
  `API_BASE` now points at the live backend permanently — the old "revert to
  localhost before committing" rule is retired. Cloudflare strips `.html`, so
  `/share.html` 307-redirects to `/share` (query params preserved — share works).
- [x] Earlier reachability path (now superseded by the deploy above): cloudflared
  quick tunnels, one per server — proven for phone testing.

**Phase 4 fixes (alongside 4-3):**
- [x] Parser language: title/ingredients/steps now stay in the caption's
  language (was translating Hebrew → English); cross-language category matching.
- [x] `/import` uses the user's **live** categories from the DB (was a stale
  hardcoded list missing "Meatballs", so it mis-fell back to Unknown).
- [x] Manual re-categorize: per-card category `<select>` (existing or new) →
  `PATCH /recipes/{id}` now also accepts `category`. `set_recipe_flags` →
  `update_recipe` (general partial update).
- [x] "Unknown" filter chip: `?category=Unknown` → recipes with null category.
- [x] Swapped the placeholder SVG icon for square **PNGs** (192/512) — Chrome's OS
  install icon wants raster squares (the SVG triggered a manifest warning).

> Note: the shared Supabase client is serialized with a lock (`storage.py`
> `@_synchronized`) — concurrent requests over its HTTP/2 connection raced into
> WinError 10035 on Windows. Don't remove it.

**Phase 5 — Sharing & polish:**
- [x] 5-1. Search: client-side filter over the loaded list (title + ingredient
  names, case-insensitive) — instant, no backend call, composes with the
  active category chip.
- [x] 5-2. Recipe editing: ✎ swaps the card for an in-place form — title input,
  ingredients + steps as plain text lines (edited ingredients saved name-only).
- [ ] 5-3. Login — **per-user recipes**: each user sees and manages only their
  own cookbook (scope changed from "shared family data"). Identity = email
  typed once, sent as `X-User` (family-trust; upgrade seam to real auth later).
  - [x] (a) DDL: `owner` text column on recipes + categories; composite
    uniques `(owner, name)` / `(owner, source_url)`.
  - [x] (b) Backend: `X-User` header filters + stamps all recipe/category rows.
  - [x] (c) Frontend: login screen → localStorage → header on every fetch.
  - [x] (d) share.html + share-queue.js carry the owner in queued POSTs.
  - [x] (e) iOS Shortcut sends the X-User header. **Proven on the iPhone.**
  - [x] (f) Delete a user (backend): `DELETE /users/{email}`, self-service
    only (X-User must match). Frontend button still TODO.
  - [ ] (g) Shareable iOS Shortcut for family (sister first): iCloud link
    install; per-person email in the X-User header — ideally via an import
    question asked at install time.

**Phase 6 — more sources (pulled forward, user request):**
- [x] 6-a/b. TikTok import: `tiktok.py` (Apify clockworks~tiktok-scraper;
  short links vm./vt./t/ resolved via redirect; canonical URL drops the
  username — post id alone is the dedupe key). `/import` dispatches through
  `_resolve_source()` — one place to add future sources. **Proven end-to-end.**
- [x] Share-queue reliability fix: the app drains the IndexedDB share queue on
  every open (visible banner) — Background Sync alone stranded shares after
  ~3 failed retries against Render cold starts.

**Phase 7 — Tags migration (one category per recipe → multiple tags):**
Decisions: full rename categories→tags (DB, API, UI); Gemini picks 1–2 tags
([] if none fits); card UI = tag chips + "+" picker; "Unknown"→"Untagged"
(= recipe with zero tags); filter chips multi-select with AND semantics.
Zero-downtime shape: rename first, then expand → dual-write → switch reads →
switch writes → contract. DDL scripts live in the session plan; run them in
the Supabase dashboard SQL editor only.
- [x] 7-1. Internal rename (Python/JS/HTML names, dict key category→tag) — zero behavior change.
- [x] 7-2. API rename: /categories→/tags, ?tag=, "Unknown"→"Untagged".
- [x] 7-3. ⚠ Cutover DDL: rename table categories→tags + column category_id→tag_id; `.table("tags")` commit (brief downtime).
- [x] 7-4. DDL: recipe_tags join table (PK recipe_id+tag_id, cascades) + backfill from tag_id (20 = 20 verified).
- [x] 7-5. Dual-write: save/update also write recipe_tags (reads unchanged).
  Gotcha found in 7-4: creating recipe_tags made the `tags(name)` embed
  ambiguous (PGRST201, two join paths) and broke GET /recipes until the
  embed named its FK path explicitly — new tables near old embeds are NOT
  automatically zero-impact.
- [x] 7-6. Switch reads: /recipes embeds a tags list from recipe_tags; "Untagged" = no join rows.
- [x] 7-7. PATCH /recipes accepts `tags: [names]` (full replacement).
- [x] 7-8. Card UI: tag chips with × + a "+" picker (replaces the dropdown).
- [x] 7-9. Filter chips multi-select: several active tags = recipes with ALL of them.
- [ ] 7-10. Gemini import returns 1–2 tags; save_recipe writes join rows, stops writing tag_id.
- [ ] 7-11. ⚠ Contract: drop recipes.tag_id; remove the detach step in delete_tag; rewrite Data model section here.

## TODO backlog — pick a task when time is convenient
> Not scheduled; grab one when there's a free moment. New "later" items land here.
- [ ] **Cold-start drill (one Android):** pause the cron-job.org keep-warm job →
  wait ~20 min (server sleeps) → share a video → do **not** open the app →
  recipe should land within ~3 min (SW v5 in-event retries) → unpause the job.
- [ ] **Full share matrix (all devices):** on every family device (Omer Android,
  family Android, Omer iPhone, sister's iPhone once 5-3g is done) share one video
  warm + one cold; verify each lands under the right owner; on Androids confirm
  `/sw-version` = `v5 cold-start-retry` first.
- [x] 5-3g — shareable iOS Shortcut for sister (iCloud link; per-person email).
  DONE 2026-07-08: tested iCloud link is now published inside the in-app
  install guide (d9b7a9d) — header "How to install" + login-screen link,
  Android/iPhone tabs with platform auto-detect. Sister self-installs from it.
- [ ] 5-3f frontend — delete-user button in the app.
- [ ] Require `X-User`: drop the `DEFAULT_OWNER` fallback + lowercase the header
  server-side (only after every phone has logged in / Shortcut updated).
- [ ] (after Phase 7) Search also matches tag names — one-liner in `applySearch`.
- [ ] (after Phase 7) `/import` duplicate response (`find_recipe_by_url`) doesn't
  embed tags — harmless; embed if a client ever needs it.

## Risks
- **Instagram fetch is free but unofficial.** yt-dlp can break when Instagram changes;
  some private/region-locked posts have no readable caption. Phase 1b proves it early.
  Mitigation: null fields + "Unknown" category.
- **Free-tier limits** (Gemini quota, Render cold-start) are fine for personal/family use.

## Verification (end-to-end, once Phase 1 lands)
1. Activate the venv, install deps from `requirements.txt`.
2. Run the FastAPI server; `POST /import` with a real public Instagram recipe URL.
3. Confirm the JSON has title, ingredients with quantities, steps, and a category from
   the fixed list.
4. Test fallback: a caption-less URL → null fields and category "Unknown".

## Environment notes
- Windows: use the `py` launcher (bare `python` is shadowed by a Store stub).
- Backend venv: `backend/.venv` — interpreter at `backend/.venv/Scripts/python.exe`.
