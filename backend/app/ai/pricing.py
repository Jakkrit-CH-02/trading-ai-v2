"""Token prices in USD per million tokens (Anthropic list prices, checked 2026-11).

Used only to *estimate* spend for the monthly budget guard; the invoice is the truth.
Unknown models are priced like the most expensive one we use, so the guard errs on the safe side.
"""

from decimal import Decimal

PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
    "claude-sonnet-5-5": (Decimal("2.00"), Decimal("10.00")),
}
FALLBACK = (Decimal("5.00"), Decimal("25.00"))
CACHE_READ_FACTOR = Decimal("0.1")  # cached input costs a tenth of normal input
MILLION = Decimal(1_000_000)


def cost_usd(model: str, tokens_in: int, tokens_out: int, cache_read: int = 0) -> Decimal:
    p_in, p_out = PRICES.get(model, FALLBACK)
    return (
        Decimal(tokens_in) * p_in + Decimal(cache_read) * p_in * CACHE_READ_FACTOR
        + Decimal(tokens_out) * p_out
    ) / MILLION  # fmt: skip
