"""Persistence layer — saves recipes into our Supabase (Postgres) database.

Isolates all database access behind simple functions (save_recipe, ...), so the
rest of the app never deals with Supabase directly. Uses the secret key, which
runs server-side only and bypasses Row Level Security.
"""

import functools
import hashlib
import os
import threading
from pathlib import Path

import requests
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


# Module-level singleton: created once, reused for every request. Creating a
# fresh client per call skipped connection pooling — each request re-paid the
# (currently ~11s) TLS/connect cost and leaked the connection, stalling the
# server. One shared client keeps the pool warm (~0.2s per query).
_client_instance: Client | None = None


def _client() -> Client:
    """Return the shared Supabase client, creating it once on first use."""
    global _client_instance
    if _client_instance is None:
        if not (SUPABASE_URL and SUPABASE_KEY):
            raise RuntimeError("SUPABASE_URL / SUPABASE_KEY missing in backend/.env")
        _client_instance = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client_instance


# The shared client uses one synchronous HTTP/2 connection, which isn't safe
# under concurrent use from FastAPI's threadpool (Windows raises WinError 10035
# when two requests race). Serialize all DB access through one lock — fine at
# personal-app scale. RLock so a decorated fn can call another without deadlock.
_lock = threading.RLock()


def _synchronized(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _lock:
            return fn(*args, **kwargs)
    return wrapper


def _tag_id(client: Client, name: str | None, owner: str) -> int | None:
    """Map OWNER's tag NAME to its id. Returns None for Untagged/no match.

    Owner-scoped: two users can each have a "Pasta" with different ids.
    This enforces the "null -> Untagged" rule at the database boundary.
    "Unknown" stays reserved too until the parser emits tags (7-10).
    """
    if not name or name in ("Untagged", "Unknown"):
        return None
    result = (
        client.table("tags")
        .select("id")
        .eq("name", name)
        .eq("owner", owner)
        .limit(1)
        .execute()
    )
    return result.data[0]["id"] if result.data else None


@_synchronized
def list_tags(*, owner: str) -> list[dict]:
    """Return OWNER's tags (id + name), sorted by name.

    A plain SELECT — the read counterpart to save_recipe's INSERT.
    """
    client = _client()
    result = (
        client.table("tags")
        .select("id, name")
        .eq("owner", owner)
        .order("name")
        .execute()
    )
    return result.data


@_synchronized
def create_tag(name: str, *, owner: str) -> dict:
    """Insert a new tag for OWNER and return the stored row (id + name).

    The write counterpart to list_tags. Duplicates are per owner (each
    user can have their own "Pasta"); they raise ValueError (endpoint turns it
    into a 409). The module lock makes the check-then-insert atomic, mirroring
    save_recipe's dedupe pattern.
    """
    client = _client()
    if _tag_id(client, name, owner) is not None:
        raise ValueError(f"tag {name!r} already exists")
    result = (
        client.table("tags").insert({"name": name, "owner": owner}).execute()
    )
    return result.data[0]


@_synchronized
def delete_tag(tag_id: int, *, owner: str) -> None:
    """Delete one of OWNER's tags; its recipes fall back to Untagged.

    Ownership is checked FIRST — before any mutation — so a wrong/foreign id
    can't detach another user's recipes (LookupError -> 404 at the endpoint).
    Then two ordered steps: detach recipes (set tag_id = null) so the
    foreign key won't block the delete, then remove the tag row. This
    enforces the plan's "null -> Untagged" rule instead of cascading deletes
    (which destroy recipes) or failing on the FK constraint.
    """
    client = _client()
    owned = (
        client.table("tags")
        .select("id")
        .eq("id", tag_id)
        .eq("owner", owner)
        .limit(1)
        .execute()
    )
    if not owned.data:
        raise LookupError(f"tag {tag_id} not found")
    client.table("recipes").update({"tag_id": None}).eq(
        "tag_id", tag_id
    ).execute()
    client.table("tags").delete().eq("id", tag_id).execute()


@_synchronized
def list_recipes(
    tag: str | None = None,
    collection: str | None = None,
    *,
    owner: str,
) -> list[dict]:
    """Return one owner's recipes (newest first), optionally filtered.

    `owner` scopes every query — users only ever see their own rows (5-3).
    `tag` filters by tag name (inner join); the special value
    "Untagged" filters to recipes with no tag (tag_id IS NULL).
    `collection` filters by a cross-cutting flag: "favorites" -> is_favorite,
    "up_next" -> is_up_next. The two are independent; used one at a time.
    """
    client = _client()
    # Inner join only when filtering by a real tag; left join otherwise so
    # Untagged (null-tag) recipes still appear.
    if tag and tag != "Untagged":
        join = "tags!inner(name)"
    else:
        join = "tags(name)"
    query = client.table("recipes").select(f"*, {join}").eq("owner", owner).order(
        "created_at", desc=True
    )
    if tag == "Untagged":
        query = query.is_("tag_id", "null")   # the untagged bucket
    elif tag:
        query = query.eq("tags.name", tag)
    if collection == "favorites":
        query = query.eq("is_favorite", True)
    elif collection == "up_next":
        query = query.eq("is_up_next", True)
    return query.execute().data


def store_thumbnail(source_url: str, thumbnail_url: str | None) -> str | None:
    """Copy an Instagram thumbnail into our own Supabase Storage bucket.

    Instagram's CDN URLs expire after days and browsers refuse to embed them
    (Cross-Origin-Resource-Policy), so at import time we download the image
    server-side and keep a permanent copy. Returns our public URL, or None on
    any failure — an import must never crash over a missing picture.

    The download runs OUTSIDE the lock — it can take up to 30s and doesn't
    touch the shared client; only the Supabase upload needs serializing.
    """
    if not thumbnail_url:
        return None
    try:
        image = requests.get(thumbnail_url, timeout=30)
        image.raise_for_status()
        # Stable filename per post: re-importing overwrites instead of piling up.
        name = hashlib.md5(source_url.encode()).hexdigest() + ".jpg"
        with _lock:
            client = _client()
            client.storage.from_("thumbnails").upload(
                name,
                image.content,
                file_options={"content-type": "image/jpeg", "upsert": "true"},
            )
            return client.storage.from_("thumbnails").get_public_url(name)
    except Exception:
        return None


@_synchronized
def find_recipe_by_url(source_url: str, *, owner: str) -> dict | None:
    """Return OWNER's stored recipe for a source_url, or None if not saved yet.

    Dedupe is per user: two family members can each save the same reel into
    their own cookbook. Lets /import short-circuit on a known duplicate BEFORE
    paying for the Apify fetch + Gemini parse (save_recipe also uses it as a
    last-line guard).
    """
    client = _client()
    result = (
        client.table("recipes")
        .select("*")
        .eq("source_url", source_url)
        .eq("owner", owner)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


@_synchronized
def save_recipe(recipe: dict, *, owner: str) -> dict:
    """Insert a parsed recipe for OWNER and return the stored row (new id).

    Idempotent on (source_url, owner): importing the same reel twice
    (double-submit, share + paste, or a Background Sync retry) returns the
    existing row instead of creating a duplicate — but different owners each
    get their own copy. The module lock makes this check-then-insert atomic
    (RLock, so the nested find_recipe_by_url call is fine).

    Args:
        recipe: dict with title, tag (name), ingredients, steps,
                source_url, thumbnail — the shape returned by POST /import.
        owner:  the saving user's identity, stamped onto the row.
    """
    client = _client()

    source_url = recipe.get("source_url")
    if source_url:
        existing = find_recipe_by_url(source_url, owner=owner)
        if existing:
            return existing          # already saved — return it, don't duplicate

    row = {
        "title": recipe.get("title"),
        "tag_id": _tag_id(client, recipe.get("tag"), owner),
        "source_url": recipe.get("source_url"),
        "thumbnail": recipe.get("thumbnail"),
        "ingredients": recipe.get("ingredients"),  # list -> stored as jsonb
        "steps": recipe.get("steps"),              # list -> stored as jsonb
        "owner": owner,
    }
    result = client.table("recipes").insert(row).execute()
    return result.data[0]


@_synchronized
def update_recipe(
    recipe_id: int,
    *,
    owner: str,
    is_favorite: bool | None = None,
    is_up_next: bool | None = None,
    tag: str | None = None,
    title: str | None = None,
    ingredients: list | None = None,
    steps: list | None = None,
) -> dict:
    """Partial-update a recipe and return the updated row.

    Only the fields passed (non-None) are written, so a caller can toggle a
    collection flag OR reassign the tag independently. `tag` is a
    NAME, mapped to tag_id here (Untagged / unrecognized name -> null),
    reusing save_recipe's rule. Keyword-only args prevent positional mix-ups.
    """
    client = _client()
    updates: dict = {}
    if is_favorite is not None:
        updates["is_favorite"] = is_favorite
    if is_up_next is not None:
        updates["is_up_next"] = is_up_next
    if tag is not None:
        updates["tag_id"] = _tag_id(client, tag, owner)
    if title is not None:
        updates["title"] = title
    if ingredients is not None:
        updates["ingredients"] = ingredients   # list -> stored as jsonb
    if steps is not None:
        updates["steps"] = steps               # list -> stored as jsonb
    if not updates:
        raise ValueError("no fields to update")
    result = (
        client.table("recipes")
        .update(updates)
        .eq("id", recipe_id)
        .eq("owner", owner)
        .execute()
    )
    if not result.data:
        # LookupError (not HTTPException): storage stays HTTP-agnostic; the
        # endpoint layer translates this into a 404. Someone else's recipe id
        # takes this same path — a 404, not a hint that the row exists.
        raise LookupError(f"recipe {recipe_id} not found")
    return result.data[0]


@_synchronized
def delete_user(owner: str) -> dict:
    """Erase every row belonging to OWNER; returns counts per table.

    Recipes go first — they reference tags via the FK, so deleting
    tags first would be blocked. Thumbnails in Storage are left behind
    as harmless orphans (stable names, overwritten on any re-import).
    """
    client = _client()
    recipes = client.table("recipes").delete().eq("owner", owner).execute()
    tags = client.table("tags").delete().eq("owner", owner).execute()
    return {"recipes": len(recipes.data), "tags": len(tags.data)}


@_synchronized
def delete_recipe(recipe_id: int, *, owner: str) -> None:
    """Delete one of OWNER's recipes by id (someone else's id is a no-op).

    Recipes are leaf rows (nothing references them), so this is a straight
    DELETE — simpler than delete_tag, which first detaches its recipes.
    """
    client = _client()
    client.table("recipes").delete().eq("id", recipe_id).eq("owner", owner).execute()


# Direct test:  py app/storage.py  — inserts one sample recipe.
if __name__ == "__main__":
    import json
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    sample = {
        "title": "Test — Spaghetti alla Nerano",
        "tag": "Pasta",
        "ingredients": [{"name": "Spaghetti", "quantity": 320, "unit": "g"}],
        "steps": ["Fry zucchini.", "Cook pasta.", "Toss with provolone."],
        "source_url": "https://www.instagram.com/reel/DZ1ydoFKh1p/",
        "thumbnail": None,
    }
    stored = save_recipe(sample, owner="omergrinwald14@gmail.com")
    print("Saved row:")
    print(json.dumps(stored, indent=2, ensure_ascii=False))
