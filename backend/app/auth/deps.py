from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.services import Services, get_services
from app.auth.core import Claims, TokenError, read_token
from app.auth.crypto import CryptoError
from app.core.models import User


def current_user(
    svc: Annotated[Services, Depends(get_services)],
    authorization: Annotated[str | None, Header()] = None,
) -> Claims:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "not authenticated", headers={"WWW-Authenticate": "Bearer"})
    try:
        return read_token(svc.settings.jwt_secret.get_secret_value(), authorization[7:], "access")
    except TokenError as e:
        raise HTTPException(
            401, "invalid or expired token", headers={"WWW-Authenticate": "Bearer"}
        ) from e


async def db_session(svc: Annotated[Services, Depends(get_services)]):  # type: ignore[no-untyped-def]
    if svc.db is None:
        raise HTTPException(503, "database not configured")
    async with svc.db() as session:
        yield session


Db = Annotated[AsyncSession, Depends(db_session)]
CurrentUser = Annotated[Claims, Depends(current_user)]


async def require_totp(
    user: CurrentUser,
    db: Db,
    svc: Annotated[Services, Depends(get_services)],
    x_totp: Annotated[str | None, Header()] = None,
) -> Claims:
    """Gate for actions that touch real money or security settings (SPEC 8): a fresh TOTP code."""
    if not x_totp:
        raise HTTPException(401, "X-TOTP header required", headers={"X-Totp-Required": "1"})
    row = await db.get(User, user.user_id)
    if row is None or row.totp_secret_enc is None:
        raise HTTPException(403, "2FA is not set up")
    try:
        secret = (
            svc.get_cipher()
            .decrypt(row.totp_secret_enc, aad=f"user:{row.id}:totp".encode())
            .decode()
        )
    except CryptoError as e:
        raise HTTPException(503, "encryption is not configured") from e
    if not svc.totp.verify(str(row.id), secret, x_totp):
        raise HTTPException(401, "invalid TOTP code", headers={"X-Totp-Required": "1"})
    return user


TotpUser = Annotated[Claims, Depends(require_totp)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
