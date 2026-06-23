# Digital CookBook

A Flask backend that turns social-media food posts into structured recipes.

**Step 1 (current):** given an Instagram reel/post URL, fetch the post's raw
caption text via a reliable third-party scraper API.

## Project structure

```
Digital_CookBook/
├── run.py                       # Dev entry point (python run.py)
├── config.py                    # Env-driven configuration
├── requirements.txt
├── .env.example                 # Copy to .env and fill in your API key
├── .gitignore
└── app/
    ├── __init__.py              # create_app() factory + blueprint registration
    ├── routes/
    │   └── recipe.py            # POST /extract-recipe, GET /health
    ├── services/
    │   ├── instagram_scraper.py # Third-party API integration (the only net call)
    │   └── exceptions.py        # Typed errors -> HTTP status codes
    └── utils/
        └── validators.py        # Instagram URL validation
```

The design isolates the scraper provider behind `services/instagram_scraper.py`.
Swapping providers only touches `_build_request` and `_parse_caption` there;
the route and validation layers stay untouched.

## Setup

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env            # then edit .env with your scraper API key
```

This project calls a **managed Instagram scraper API** rather than scraping
Instagram directly — direct scraping is unreliable (login walls, rate limits,
changing markup) and against Instagram's ToS. The `.env.example` is written for
a RapidAPI-style provider; any provider works once you map its request/response
shape in `services/instagram_scraper.py`.

## Run

```bash
python run.py
# serves on http://localhost:5000
```

## API

### `POST /extract-recipe`

Request:
```json
{ "url": "https://www.instagram.com/reel/Cabc123/" }
```

Success `200`:
```json
{ "success": true, "url": "...", "caption": "Raw caption text..." }
```

Error `4xx/5xx`:
```json
{ "success": false, "error": "Human-readable reason" }
```

| Situation                       | Status |
|---------------------------------|--------|
| Missing / non-JSON body         | 400    |
| Invalid Instagram URL           | 400    |
| Private account                 | 403    |
| Post not found / deleted        | 404    |
| Scraper rate-limited / upstream | 502    |
| Scraper timeout                 | 504    |

Example:
```bash
curl -X POST http://localhost:5000/extract-recipe \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.instagram.com/reel/Cabc123/"}'
```

### `GET /health`

Returns `{ "status": "ok" }` for uptime checks.
