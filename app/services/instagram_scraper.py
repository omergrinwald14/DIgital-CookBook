"""Instagram caption scraper.

Why a third-party API?
----------------------
Instagram actively blocks direct scraping (rate limits, login walls, frequent
markup changes). A managed scraper API handles proxies, retries and auth for us
and returns clean JSON, which is far more *reliable* for production use.

This module is the single integration point with that provider. If you ever
switch providers, only `_build_request` and `_parse_caption` should need to
change — the public `fetch_caption` contract stays the same.
"""

import requests
from flask import current_app

from app.services.exceptions import (
    InvalidUrlError,
    PostNotFoundError,
    PrivatePostError,
    ScraperError,
    ScraperTimeoutError,
)
from app.utils.validators import is_valid_instagram_url


def fetch_caption(url: str) -> str:
    """Fetch the raw caption text for an Instagram post/reel.

    Args:
        url: A public Instagram post, reel, or video URL.

    Returns:
        The raw caption text of the post.

    Raises:
        InvalidUrlError:    URL is empty or not a valid Instagram URL.
        PrivatePostError:   The post is from a private account.
        PostNotFoundError:  The post doesn't exist / was removed.
        ScraperTimeoutError: The provider didn't respond in time.
        ScraperError:       Any other upstream/parse failure.
    """
    # --- 1. Validate before spending an API call ---
    if not is_valid_instagram_url(url):
        raise InvalidUrlError("Please provide a valid Instagram post or reel URL.")

    # --- 2. Read provider config (set in .env / environment) ---
    api_url = current_app.config.get("SCRAPER_API_URL")
    api_key = current_app.config.get("SCRAPER_API_KEY")
    api_host = current_app.config.get("SCRAPER_API_HOST")
    timeout = current_app.config.get("SCRAPER_TIMEOUT", 20)

    if not api_url or not api_key:
        # A configuration problem, not the caller's fault.
        raise ScraperError("Scraper API is not configured. Check SCRAPER_API_* env vars.")

    request_kwargs = _build_request(url, api_url, api_key, api_host, timeout)

    # --- 3. Call the provider, translating transport errors into our types ---
    try:
        response = requests.get(**request_kwargs)
    except requests.Timeout as exc:
        raise ScraperTimeoutError("The scraper API timed out. Please try again.") from exc
    except requests.RequestException as exc:
        raise ScraperError("Could not reach the scraper API.") from exc

    # --- 4. Map common HTTP failures to meaningful errors ---
    _raise_for_status(response)

    # --- 5. Parse JSON and pull out the caption ---
    try:
        payload = response.json()
    except ValueError as exc:
        raise ScraperError("Scraper API returned a malformed response.") from exc

    return _parse_caption(payload)


def _build_request(url, api_url, api_key, api_host, timeout) -> dict:
    """Assemble the requests.get(**kwargs) for the configured provider.

    Written for a RapidAPI-style provider that takes the target post URL as a
    query parameter and the API key in headers. Adapt this single function if
    your provider expects a different shape.
    """
    headers = {"x-rapidapi-key": api_key}
    if api_host:
        headers["x-rapidapi-host"] = api_host

    return {
        "url": api_url,
        "headers": headers,
        "params": {"code_or_id_or_url": url},
        "timeout": timeout,
    }


def _raise_for_status(response: "requests.Response") -> None:
    """Translate provider HTTP status codes into our exception hierarchy."""
    if response.ok:
        return

    status = response.status_code
    # Providers differ, but these are the most common signals.
    if status in (401, 403):
        raise PrivatePostError("This post is private or cannot be accessed.")
    if status == 404:
        raise PostNotFoundError("This post could not be found. It may have been deleted.")
    if status == 429:
        raise ScraperError("Rate limit reached on the scraper API. Try again shortly.")

    raise ScraperError(f"Scraper API returned an unexpected error (HTTP {status}).")


def _parse_caption(payload: dict) -> str:
    """Extract the caption string from the provider's JSON payload.

    Provider response shapes vary, so we defensively probe a few common
    locations. Adjust the candidate paths to match your provider's schema.
    """
    # Some providers wrap the post under a "data" key.
    data = payload.get("data", payload) if isinstance(payload, dict) else {}

    # Detect a private/unavailable post reported in the body (HTTP 200 + flag).
    if isinstance(data, dict) and data.get("is_private"):
        raise PrivatePostError("This post is private or cannot be accessed.")

    caption = _first_present(
        data,
        # Flat fields seen across providers.
        ["caption_text", "caption", "title", "description"],
    )

    # Nested shape: {"caption": {"text": "..."}}
    if caption is None:
        nested = data.get("caption") if isinstance(data, dict) else None
        if isinstance(nested, dict):
            caption = nested.get("text")

    # Instagram GraphQL-style: edge_media_to_caption -> edges[0] -> node -> text
    if caption is None and isinstance(data, dict):
        edges = (data.get("edge_media_to_caption") or {}).get("edges")
        if edges:
            caption = edges[0].get("node", {}).get("text")

    if not caption:
        # Reached the provider successfully but found no caption — treat as a
        # soft failure rather than crashing, so the caller can react.
        raise ScraperError("No caption was found on this post.")

    return caption.strip()


def _first_present(data: dict, keys: list):
    """Return the first non-empty value among `keys` in `data`, else None."""
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value:
            return value
    return None
