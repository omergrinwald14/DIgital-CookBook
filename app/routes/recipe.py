"""Recipe extraction routes.

This blueprint exposes the public HTTP surface for turning an Instagram link
into recipe data. For this first step it returns the raw caption; later steps
will layer parsing/structuring on top.
"""

from flask import Blueprint, jsonify, request

from app.services.exceptions import ScraperError
from app.services.instagram_scraper import fetch_caption

recipe_bp = Blueprint("recipe", __name__)


@recipe_bp.route("/extract-recipe", methods=["POST"])
def extract_recipe():
    """Accept an Instagram URL and return the post's raw caption text.

    Request body (JSON):
        { "url": "https://www.instagram.com/reel/XXXX/" }

    Success (200):
        { "success": true, "url": "...", "caption": "..." }

    Failure (4xx/5xx):
        { "success": false, "error": "human-readable reason" }
    """
    # Guard against non-JSON or empty bodies before touching the data.
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(success=False, error="Request body must be valid JSON."), 400

    url = data.get("url")
    if not url or not isinstance(url, str):
        return jsonify(success=False, error="Missing required field: 'url'."), 400

    # Delegate the heavy lifting to the service layer. We only translate its
    # outcome (value or typed exception) into an HTTP response here.
    try:
        caption = fetch_caption(url)
    except ScraperError as exc:
        # Every scraper failure carries its own suggested status code.
        return jsonify(success=False, error=exc.message), exc.status_code

    return jsonify(success=True, url=url, caption=caption), 200


@recipe_bp.route("/health", methods=["GET"])
def health():
    """Lightweight liveness probe for uptime checks / deployment platforms."""
    return jsonify(status="ok"), 200
