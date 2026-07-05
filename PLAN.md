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
- [ ] 5-2. Recipe editing: edit title, ingredients, steps in-place.
- [ ] 5-3. Family login (Supabase auth; protects the write endpoints).

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
