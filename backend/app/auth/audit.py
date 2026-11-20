from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AuditLog

_SECRET_KEYS = ("secret", "password", "key", "token", "totp")


def scrub(d: dict[str, Any] | None) -> dict[str, Any] | None:
    """Audit rows must never carry credentials, even if a caller passes them by mistake."""
    if d is None:
        return None
    return {k: "***" if any(s in k.lower() for s in _SECRET_KEYS) else v for k, v in d.items()}


def audit(
    session: AsyncSession,
    user_id: UUID | None,
    action: str,
    target: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Adds an append-only audit row to the caller's transaction (commit with the change)."""
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            target=target,
            before=scrub(before),
            after=scrub(after),
            ip=ip,
        )
    )
