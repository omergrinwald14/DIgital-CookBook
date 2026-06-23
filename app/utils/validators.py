"""URL validation helpers.

Kept separate from the scraper so the validation rules can be unit-tested in
isolation and reused elsewhere (e.g. a future batch-import feature).
"""

import re

# Matches the canonical Instagram post / reel / TV URL shapes and captures the
# shortcode, e.g. the "Cxyz123" in https://www.instagram.com/reel/Cxyz123/.
# Accepts optional "www.", trailing slash, and query string.
_INSTAGRAM_URL_RE = re.compile(
    r"^https?://(?:www\.)?instagram\.com/"
    r"(?:reel|reels|p|tv)/"
    r"(?P<shortcode>[A-Za-z0-9_-]+)"
    r"/?(?:\?.*)?$",
    re.IGNORECASE,
)


def is_valid_instagram_url(url: str) -> bool:
    """Return True if `url` looks like a public Instagram post/reel/video URL."""
    return bool(url) and bool(_INSTAGRAM_URL_RE.match(url.strip()))


def extract_shortcode(url: str):
    """Return the post shortcode from an Instagram URL, or None if it doesn't match."""
    if not url:
        return None
    match = _INSTAGRAM_URL_RE.match(url.strip())
    return match.group("shortcode") if match else None
