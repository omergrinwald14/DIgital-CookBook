"""Persistence layer — saves recipes into our Supabase (Postgres) database.

Isolates all database access behind simple functions (save_recipe, ...), so the
rest of the app never deals with Supabase directly. Uses the secret key, which
runs server-side only and bypasses Row Level Security.
"""

import os
from pathlib import Path

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


def _category_id(client: Client, name: str | None) -> int | None:
    """Map a category NAME to its id. Returns None for Unknown/no match.

    This enforces the "null -> Unknown" rule at the database boundary.
    """
    if not name or name == "Unknown":
        return None
    result = client.table("categories").select("id").eq("name", name).limit(1).execute()
    return result.data[0]["id"] if result.data else None


def list_categories() -> list[dict]:
    """Return every category (id + name), sorted by name.

    A plain SELECT — the read counterpart to save_recipe's INSERT.
    """
    client = _client()
    result = client.table("categories").select("id, name").order("name").execute()
    return result.data


def create_category(name: str) -> dict:
    """Insert a new category and return the stored row (id + name).

    The write counterpart to list_categories. Mirrors save_recipe's INSERT
    pattern. Input validation (empty/duplicate names) lives at the endpoint
    layer (5c), keeping this function a thin DB operation.
    """
    client = _client()
    result = client.table("categories").insert({"name": name}).execute()
    return result.data[0]


def delete_category(category_id: int) -> None:
    """Delete a category; its recipes fall back to Unknown (category_id null).

    Two ordered steps: first detach recipes (set category_id = null) so the
    foreign key won't block the delete, then remove the category row. This
    enforces the plan's "null -> Unknown" rule instead of cascading deletes
    (which destroy recipes) or failing on the FK constraint.
    """
    client = _client()
    client.table("recipes").update({"category_id": None}).eq(
        "category_id", category_id
    ).execute()
    client.table("categories").delete().eq("id", category_id).execute()


def list_recipes(category: str | None = None) -> list[dict]:
    """Return recipes (newest first), optionally filtered by category name.

    Joins in each recipe's category name so the frontend needn't map ids.
    When filtering, '!inner' forces an inner join so non-matching recipes are
    excluded; a plain join only nulls the category and keeps the row.
    """
    client = _client()
    # Inner join only when filtering; left join otherwise so Unknown
    # (null-category) recipes still appear in the full list.
    join = "categories!inner(name)" if category else "categories(name)"
    query = client.table("recipes").select(f"*, {join}").order(
        "created_at", desc=True
    )
    if category:
        query = query.eq("categories.name", category)
    return query.execute().data


def save_recipe(recipe: dict) -> dict:
    """Insert a parsed recipe and return the stored row (with its new id).

    Args:
        recipe: dict with title, category (name), ingredients, steps,
                source_url, thumbnail — the shape returned by POST /import.
    """
    client = _client()
    row = {
        "title": recipe.get("title"),
        "category_id": _category_id(client, recipe.get("category")),
        "source_url": recipe.get("source_url"),
        "thumbnail": recipe.get("thumbnail"),
        "ingredients": recipe.get("ingredients"),  # list -> stored as jsonb
        "steps": recipe.get("steps"),              # list -> stored as jsonb
    }
    result = client.table("recipes").insert(row).execute()
    return result.data[0]


# Direct test:  py app/storage.py  — inserts one sample recipe.
if __name__ == "__main__":
    import json
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    sample = {
        "title": "Test — Spaghetti alla Nerano",
        "category": "Pasta",
        "ingredients": [{"name": "Spaghetti", "quantity": 320, "unit": "g"}],
        "steps": ["Fry zucchini.", "Cook pasta.", "Toss with provolone."],
        "source_url": "https://www.instagram.com/reel/DZ1ydoFKh1p/",
        "thumbnail": None,
    }
    stored = save_recipe(sample)
    print("Saved row:")
    print(json.dumps(stored, indent=2, ensure_ascii=False))
