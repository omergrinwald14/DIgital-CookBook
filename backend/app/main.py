"""FastAPI application — the HTTP entry point for the Digital CookBook backend.

It exposes the recipe pipeline as a web API so the frontend (and later the
phone's Share button) can use it. The heavy lifting lives in the imported
modules; this file just wires them together behind endpoints.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.instagram import fetch_caption, normalize_instagram_url
from app.parser import parse_recipe
from app.storage import (
    create_category,
    delete_category,
    delete_recipe,
    find_recipe_by_url,
    list_categories,
    list_recipes,
    save_recipe,
    store_thumbnail,
    update_recipe,
)

app = FastAPI(title="Digital CookBook API")

# Allow the browser frontend (a different origin) to call this API.
# Any origin, deliberately: the API is public until Phase 5 adds auth, and
# CORS wouldn't stop non-browser clients (curl, iOS Shortcut) anyway.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ImportRequest(BaseModel):
    """Shape of the JSON body for POST /import. Pydantic validates it for us."""
    url: str


class CategoryRequest(BaseModel):
    """Body for POST /categories — the new category's name."""
    name: str


class Ingredient(BaseModel):
    """One ingredient — same shape the parser emits, so edits stay compatible."""
    name: str
    quantity: float | None = None
    unit: str | None = None


class RecipePatch(BaseModel):
    """Body for PATCH /recipes/{id} — any subset of fields to update."""
    is_favorite: bool | None = None
    is_up_next: bool | None = None
    category: str | None = None
    title: str | None = None
    ingredients: list[Ingredient] | None = None
    steps: list[str] | None = None


@app.get("/")
def health() -> dict:
    """Simple health check — confirms the server is running."""
    return {"status": "ok"}


@app.get("/categories")
def get_categories() -> list[dict]:
    """List the fixed categories the frontend offers for browsing."""
    return list_categories()


@app.post("/categories", status_code=201)
def add_category(body: CategoryRequest) -> dict:
    """Create a category and return the stored row (id + name).

    Validation lives here at the endpoint: blank names are rejected with 400
    before we touch the DB. 201 = 'Created', the correct status for a POST
    that makes a new resource.
    """
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty.")
    try:
        return create_category(name)
    except ValueError:
        # 409 Conflict = "the resource already exists" — the standard answer
        # to a duplicate create, distinct from 400 (malformed input).
        raise HTTPException(status_code=409, detail=f'Category "{name}" already exists.')


@app.delete("/categories/{category_id}")
def remove_category(category_id: int) -> dict:
    """Delete a category by id; its recipes fall back to Unknown."""
    delete_category(category_id)
    return {"status": "deleted", "id": category_id}


@app.get("/recipes")
def get_recipes(
    category: str | None = None, collection: str | None = None
) -> list[dict]:
    """List recipes, filtered by ?category=<name> or ?collection=favorites|up_next."""
    return list_recipes(category, collection)


@app.patch("/recipes/{recipe_id}")
def patch_recipe(recipe_id: int, body: RecipePatch) -> dict:
    """Update a recipe: flags, category, and/or edited title/ingredients/steps."""
    # exclude_unset = only fields the client actually sent, so this 400 check
    # doesn't need updating every time RecipePatch grows a field.
    if not body.model_dump(exclude_unset=True):
        raise HTTPException(status_code=400, detail="No fields provided.")
    if body.title is not None and not body.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty.")
    try:
        return update_recipe(
            recipe_id,
            is_favorite=body.is_favorite,
            is_up_next=body.is_up_next,
            category=body.category,
            title=body.title.strip() if body.title else None,
            ingredients=(
                [i.model_dump() for i in body.ingredients]
                if body.ingredients is not None else None
            ),
            steps=body.steps,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Recipe not found.")


@app.delete("/recipes/{recipe_id}")
def remove_recipe(recipe_id: int) -> dict:
    """Delete a recipe by id."""
    delete_recipe(recipe_id)
    return {"status": "deleted", "id": recipe_id}


@app.post("/import")
def import_recipe(body: ImportRequest) -> dict:
    """Fetch an Instagram post and return it as a structured recipe.

    Pipeline: URL -> fetch_caption (Apify) -> parse_recipe (Gemini) -> recipe.
    """
    try:
        url = normalize_instagram_url(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Early dedupe: a known URL returns the saved row immediately, skipping
    # the Apify fetch + Gemini parse (seconds + quota saved on every retry).
    existing = find_recipe_by_url(url)
    if existing:
        return existing

    meta = fetch_caption(url)
    category_names = [c["name"] for c in list_categories()]
    recipe = parse_recipe(meta["caption"], category_names)

    # Merge the two sources: parsed recipe fields + fetch metadata (link/thumb).
    merged = {
        "title": recipe.get("title") or meta.get("title"),
        "category": recipe.get("category"),
        "ingredients": recipe.get("ingredients"),
        "steps": recipe.get("steps"),
        "source_url": meta.get("source_url"),
        "thumbnail": store_thumbnail(meta.get("source_url"), meta.get("thumbnail")),
    }

    # Persist it and return the stored row (now with a real id + created_at).
    return save_recipe(merged)
