"""FastAPI application — the HTTP entry point for the Digital CookBook backend.

It exposes the recipe pipeline as a web API so the frontend (and later the
phone's Share button) can use it. The heavy lifting lives in the imported
modules; this file just wires them together behind endpoints.
"""

from fastapi import FastAPI
from pydantic import BaseModel

from app.instagram import fetch_caption
from app.parser import parse_recipe

# Temporary fixed category list. In Phase 3 these come from the user's in-app
# list / database; hardcoded here so we can test the full pipeline now.
CATEGORIES = [
    "Pasta", "Soup", "Salad", "Dessert",
    "Chicken", "Beef", "Breakfast", "Drinks",
]

app = FastAPI(title="Digital CookBook API")


class ImportRequest(BaseModel):
    """Shape of the JSON body for POST /import. Pydantic validates it for us."""
    url: str


@app.get("/")
def health() -> dict:
    """Simple health check — confirms the server is running."""
    return {"status": "ok"}


@app.post("/import")
def import_recipe(body: ImportRequest) -> dict:
    """Fetch an Instagram post and return it as a structured recipe.

    Pipeline: URL -> fetch_caption (Apify) -> parse_recipe (Gemini) -> recipe.
    """
    meta = fetch_caption(body.url)
    recipe = parse_recipe(meta["caption"], CATEGORIES)

    # Merge the two sources: parsed recipe fields + fetch metadata (link/thumb).
    return {
        "title": recipe.get("title") or meta.get("title"),
        "category": recipe.get("category"),
        "ingredients": recipe.get("ingredients"),
        "steps": recipe.get("steps"),
        "source_url": meta.get("source_url"),
        "thumbnail": meta.get("thumbnail"),
    }
