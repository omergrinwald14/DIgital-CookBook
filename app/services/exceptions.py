"""Custom exceptions for the scraper service.

These let the service layer signal *why* something failed without knowing
anything about HTTP. The route layer maps each one to an appropriate status
code, keeping the two concerns decoupled.
"""


class ScraperError(Exception):
    """Base class for all scraper failures.

    Attributes:
        message:     Human-readable explanation, safe to return to the client.
        status_code: Suggested HTTP status the route layer should respond with.
    """

    status_code = 502  # Bad Gateway: an upstream (the scraper API) misbehaved.

    def __init__(self, message="Failed to fetch the Instagram post."):
        super().__init__(message)
        self.message = message


class InvalidUrlError(ScraperError):
    """The supplied URL is missing or is not a valid Instagram post/reel URL."""

    status_code = 400  # Bad Request: the caller gave us something unusable.


class PostNotFoundError(ScraperError):
    """The post does not exist or was deleted."""

    status_code = 404


class PrivatePostError(ScraperError):
    """The post belongs to a private account and cannot be read."""

    status_code = 403


class ScraperTimeoutError(ScraperError):
    """The scraper API did not respond in time."""

    status_code = 504  # Gateway Timeout.
