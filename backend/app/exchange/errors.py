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


class OrderRejected(ExchangeError):
    """The exchange refused an order (filter violation, insufficient balance, would-trigger...)."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class UnknownOrder(ExchangeError):
    """No order with this client order id (not placed, or purged)."""


class LiveTradingForbidden(ExchangeError):
    """A trading adapter was pointed at a host that is not the Binance testnet.

    Until Gate B (SPEC 13) only testnet is allowed; this is enforced in code, not docs."""
