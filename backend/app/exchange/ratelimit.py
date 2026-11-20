"""Used-weight tracking. Slow down once usage passes 80% of the limit (SPEC 8.3)."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping


class WeightTracker:
    def __init__(
        self,
        limit: int = 6000,
        threshold: float = 0.8,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.limit = limit
        self.threshold = threshold
        self.used = 0
        self._sleep = sleep
        self._clock = clock

    def update_from_headers(self, headers: Mapping[str, str]) -> None:
        value = headers.get("x-mbx-used-weight-1m")
        if value is not None:
            self.used = int(value)

    @property
    def should_throttle(self) -> bool:
        return self.used >= self.limit * self.threshold

    async def wait_if_needed(self) -> None:
        """Weight resets each minute; sleep to the next minute boundary when hot."""
        if self.should_throttle:
            await self._sleep(60 - (self._clock() % 60) + 0.5)
            self.used = 0
