"""Application configuration.

All runtime settings are read from environment variables (loaded from a local
`.env` file in development via python-dotenv). Keeping config in one place makes
it easy to swap scraper providers or tweak timeouts without hunting through code.
"""

import os

from dotenv import load_dotenv

# Load variables from a .env file if present. In production these are normally
# injected by the host environment, so a missing file is not an error.
load_dotenv()


class Config:
    """Central config object consumed by the Flask app factory."""

    # --- Third-party scraper API settings ---
    SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "")
    SCRAPER_API_HOST = os.getenv("SCRAPER_API_HOST", "")
    SCRAPER_API_URL = os.getenv("SCRAPER_API_URL", "")

    # How long (seconds) to wait on the scraper API before giving up.
    SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "20"))

    # --- Flask settings ---
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
