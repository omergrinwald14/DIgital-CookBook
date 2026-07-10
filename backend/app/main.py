"""FastAPI application — the HTTP entry point for the Digital CookBook backend.

It exposes the recipe pipeline as a web API so the frontend (and later the
phone's Share button) can use it. The heavy lifting lives in the imported
modules; this file just wires them together behind endpoints.
"""

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.instagram import fetch_caption as fetch_instagram
from app.instagram import normalize_instagram_url
from app.parser import parse_recipe
from app.tiktok import fetch_caption as fetch_tiktok
from app.tiktok import normalize_tiktok_url
from app.storage import (
    create_tag,
    delete_recipe,
    delete_tag,
    delete_user,
    find_recipe_by_url,
    list_recipes,
    list_tags,
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


# Identity (5-3, family-trust model): who is calling = the X-User header, an
# email the frontend will store after a one-time login screen. No password —
# the threat model is "typo", not "attacker". Upgrading to real auth later
# only changes this one function.
DEFAULT_OWNER = "omergrinwald14@gmail.com"


def current_user(x_user: str = Header(default=DEFAULT_OWNER)) -> str:
    """The requesting user, from the X-User header.

    Missing/blank header falls back to DEFAULT_OWNER so clients that predate
    login (current frontend, queued shares, iOS Shortcut) keep working during
    the migration; the default goes away once steps c–e send the header.
    """
    return x_user.strip() or DEFAULT_OWNER


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
def get_categories(user: str = Depends(current_user)) -> list[dict]:
    """List the caller's tags for browsing."""
    return list_tags(owner=user)


@app.post("/categories", status_code=201)
def add_category(body: CategoryRequest, user: str = Depends(current_user)) -> dict:
    """Create a category and return the stored row (id + name).

    Validation lives here at the endpoint: blank names are rejected with 400
    before we touch the DB. 201 = 'Created', the correct status for a POST
    that makes a new resource.
    """
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty.")
    try:
        return create_tag(name, owner=user)
    except ValueError:
        # 409 Conflict = "the resource already exists" — the standard answer
        # to a duplicate create, distinct from 400 (malformed input).
        raise HTTPException(status_code=409, detail=f'Category "{name}" already exists.')


@app.delete("/categories/{category_id}")
def remove_category(category_id: int, user: str = Depends(current_user)) -> dict:
    """Delete one of the caller's categories; its recipes fall back to Unknown."""
    try:
        delete_tag(category_id, owner=user)
    except LookupError:
        raise HTTPException(status_code=404, detail="Category not found.")
    return {"status": "deleted", "id": category_id}


@app.get("/recipes")
def get_recipes(
    category: str | None = None,
    collection: str | None = None,
    user: str = Depends(current_user),
) -> list[dict]:
    """List the caller's recipes, filtered by ?category= or ?collection=."""
    return list_recipes(category, collection, owner=user)


@app.patch("/recipes/{recipe_id}")
def patch_recipe(
    recipe_id: int, body: RecipePatch, user: str = Depends(current_user)
) -> dict:
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
            owner=user,
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
def remove_recipe(recipe_id: int, user: str = Depends(current_user)) -> dict:
    """Delete one of the caller's recipes by id."""
    delete_recipe(recipe_id, owner=user)
    return {"status": "deleted", "id": recipe_id}


@app.delete("/users/{email}")
def remove_user(email: str, user: str = Depends(current_user)) -> dict:
    """Delete a user = erase all their rows (5-3f; backend-only for now).

    Self-service only: X-User must match the email being deleted, so one
    family member can't wipe another's cookbook (403 otherwise).
    """
    email = email.strip().lower()
    if email != user.lower():
        raise HTTPException(
            status_code=403, detail="You can only delete your own data."
        )
    counts = delete_user(email)
    return {"status": "deleted", "user": email, **counts}


def _resolve_source(raw_url: str):
    """Map a raw shared link to (canonical URL, fetcher).

    One place per supported source: try each normalizer until one claims the
    URL. Adding a future source = one more except-branch here, nothing else.
    """
    try:
        return normalize_instagram_url(raw_url), fetch_instagram
    except ValueError:
        try:
            return normalize_tiktok_url(raw_url), fetch_tiktok
        except ValueError:
            raise ValueError(f"Not an Instagram or TikTok post link: {raw_url!r}")


@app.post("/import")
def import_recipe(body: ImportRequest, user: str = Depends(current_user)) -> dict:
    """Fetch an Instagram/TikTok post and return it as a structured recipe.

    Pipeline: URL -> fetch (Apify) -> parse_recipe (Gemini) -> recipe.
    """
    try:
        url, fetch = _resolve_source(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Early dedupe: a known URL returns the saved row immediately, skipping
    # the Apify fetch + Gemini parse (seconds + quota saved on every retry).
    existing = find_recipe_by_url(url, owner=user)
    if existing:
        return existing

    meta = fetch(url)
    tag_names = [t["name"] for t in list_tags(owner=user)]
    recipe = parse_recipe(meta["caption"], tag_names)

    # Merge the two sources: parsed recipe fields + fetch metadata (link/thumb).
    merged = {
        "title": recipe.get("title") or meta.get("title"),
        "tag": recipe.get("tag"),
        "ingredients": recipe.get("ingredients"),
        "steps": recipe.get("steps"),
        "source_url": meta.get("source_url"),
        "thumbnail": store_thumbnail(meta.get("source_url"), meta.get("thumbnail")),
    }

    # Persist it and return the stored row (now with a real id + created_at).
    return save_recipe(merged, owner=user)
