"""Turn a raw recipe caption into structured data using Google Gemini.

This module isolates all LLM logic. It receives the messy caption text plus the
user's fixed category list, and returns clean structured JSON:
ingredients (name/quantity/unit), ordered steps, a title, and a category that is
ALWAYS one of the allowed categories (or "Unknown").
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = "gemini-2.5-flash"  # fast, free-tier-friendly model


def _build_prompt(caption: str, categories: list[str]) -> str:
    """Construct the instruction we send to Gemini.

    The prompt pins down (a) the exact JSON shape and (b) the allowed category
    list, so the model cannot invent categories or formats — "constrained output".
    """
    category_list = ", ".join(categories)
    return f"""You parse cooking-video captions into structured recipes.

From the caption below, extract:
- "title": a short dish name (string)
- "ingredients": a list of objects, each {{"name": str, "quantity": number or null, "unit": str or null}}
- "steps": an ordered list of short instruction strings
- "category": EXACTLY ONE of these allowed categories: [{category_list}].
  If none clearly fits, use "Unknown".

Rules:
- Return ONLY valid JSON, no commentary.
- If the caption contains no actual recipe, return:
  {{"title": null, "ingredients": null, "steps": null, "category": "Unknown"}}

CAPTION:
\"\"\"{caption}\"\"\"
"""


def parse_recipe(caption: str, categories: list[str]) -> dict:
    """Parse a caption into a structured recipe dict.

    Args:
        caption: The raw Instagram caption text.
        categories: The user's fixed category list (e.g. ["Pasta", "Soup"]).

    Returns:
        Dict with keys: title, ingredients, steps, category. The category is
        guaranteed to be one of `categories` or "Unknown".
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to backend/.env")

    if not caption:
        # No caption to parse → follow the Unknown/null fallback rule.
        return {"title": None, "ingredients": None, "steps": None, "category": "Unknown"}

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=MODEL,
        contents=_build_prompt(caption, categories),
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )

    data = json.loads(response.text)

    # Safety net: enforce our rule even if the model strays.
    if data.get("category") not in categories:
        data["category"] = "Unknown"

    return data


# Direct test:  py app/parser.py
if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    sample_caption = (
        "Spaghetti alla Nerano. Fry thin zucchini rounds in olive oil with garlic "
        "until golden. Cook 320g spaghetti until al dente. Toss with butter, the "
        "fried zucchini, pasta water and grated provolone to make a creamy sauce. "
        "Top with basil. #pasta #italianfood"
    )
    sample_categories = ["Pasta", "Soup", "Salad", "Dessert", "Chicken", "Breakfast"]

    result = parse_recipe(sample_caption, sample_categories)
    print(json.dumps(result, indent=2, ensure_ascii=False))
