"""Development entry point.

Run locally with:  python run.py
For production, serve the factory with a WSGI server, e.g.:
    gunicorn "app:create_app()"

Note: the entry point is intentionally named run.py (not app.py) to avoid a
name clash with the `app/` package.
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    # host=0.0.0.0 makes the server reachable from other devices on the LAN
    # (handy when testing from a phone). Debug is driven by FLASK_DEBUG.
    app.run(host="0.0.0.0", port=5000, debug=app.config["DEBUG"])
