class ExchangeError(Exception):
    """Base class for exchange failures. Never swallowed silently."""


class RateLimited(ExchangeError):
    """HTTP 429. Back off for ``retry_after`` seconds and pause new orders."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class IPBanned(ExchangeError):
    """HTTP 418. Stop immediately (SPEC 3.3)."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"IP banned, retry after {retry_after}s")
        self.retry_after = retry_after
