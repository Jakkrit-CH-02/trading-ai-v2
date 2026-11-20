"""Telegram alerts. The bot token is never logged and never placed in an exception message."""

from typing import Protocol

import httpx
import structlog

log = structlog.get_logger()


class Notifier(Protocol):
    async def send(self, text: str) -> None: ...


class NullNotifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, client: httpx.AsyncClient | None = None) -> None:
        self.__token = token
        self._chat = chat_id
        self._http = client or httpx.AsyncClient(timeout=5.0)

    def __repr__(self) -> str:
        return f"TelegramNotifier(chat={self._chat!r})"

    async def send(self, text: str) -> None:
        """Best effort: an alert failure must never break the action that raised it."""
        try:
            res = await self._http.post(
                f"https://api.telegram.org/bot{self.__token}/sendMessage",
                json={"chat_id": self._chat, "text": text},
            )
            res.raise_for_status()
        except httpx.HTTPError as e:
            log.warning(
                "telegram_send_failed", error=type(e).__name__
            )  # not str(e): it holds the URL


def make_notifier(token: str, chat_id: str) -> Notifier:
    return TelegramNotifier(token, chat_id) if token and chat_id else NullNotifier()
