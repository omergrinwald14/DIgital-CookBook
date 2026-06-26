"""FastAPI application — the HTTP entry point for the Digital CookBook backend.

It exposes the recipe pipeline as a web API so the frontend (and later the
phone's Share button) can use it. The heavy lifting lives in the imported
modules; this file just wires them together behind endpoints.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.instagram import fetch_caption
from app.parser import parse_recipe
from app.storage import list_categories, list_recipes, save_recipe

# Temporary fixed category list. In Phase 3 these come from the user's in-app
# list / database; hardcoded here so we can test the full pipeline now.
CATEGORIES = [
    "Pasta", "Soup", "Salad", "Dessert",
    "Chicken", "Beef", "Breakfast", "Drinks",
]

app = FastAPI(title="Digital CookBook API")

# Allow the browser frontend (a different origin) to call this API.
# Dev-permissive: any origin. Tighten to the real frontend URL before deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ImportRequest(BaseModel):
    """Shape of the JSON body for POST /import. Pydantic validates it for us."""
    url: str


@app.get("/")
def health() -> dict:
    """Simple health check — confirms the server is running."""
    return {"status": "ok"}


@app.get("/categories")
def get_categories() -> list[dict]:
    """List the fixed categories the frontend offers for browsing."""
    return list_categories()


@app.get("/recipes")
def get_recipes(category: str | None = None) -> list[dict]:
    """List saved recipes, optionally filtered by ?category=<name>."""
    return list_recipes(category)


@app.post("/import")
def import_recipe(body: ImportRequest) -> dict:
    """Fetch an Instagram post and return it as a structured recipe.

    Pipeline: URL -> fetch_caption (Apify) -> parse_recipe (Gemini) -> recipe.
    """
    meta = fetch_caption(body.url)
    recipe = parse_recipe(meta["caption"], CATEGORIES)

    # Merge the two sources: parsed recipe fields + fetch metadata (link/thumb).
    merged = {
        "title": recipe.get("title") or meta.get("title"),
        "category": recipe.get("category"),
        "ingredients": recipe.get("ingredients"),
        "steps": recipe.get("steps"),
        "source_url": meta.get("source_url"),
        "thumbnail": meta.get("thumbnail"),
    }

    # Persist it and return the stored row (now with a real id + created_at).
    return save_recipe(merged)
