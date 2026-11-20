import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.api.services import Services, get_services
from app.auth.audit import audit
from app.auth.core import (
    SESSION_TTL,
    TokenError,
    hash_password,
    make_token,
    new_totp_secret,
    read_token,
    totp_uri,
    verify_password,
)
from app.auth.crypto import CryptoError
from app.auth.deps import CurrentUser, Db, TotpUser, client_ip
from app.core.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
COOKIE = "refresh_token"
Svc = Annotated[Services, Depends(get_services)]
# verified against when the e-mail is unknown, so response time does not reveal which e-mails exist
_DUMMY_HASH = hash_password(secrets.token_hex(16))


class LoginIn(BaseModel):
    email: str
    password: str
    totp: str


class TokenOut(BaseModel):
    access_token: str
    expires_in: int
    email: str


class MeOut(BaseModel):
    id: str
    email: str


class TotpSetupOut(BaseModel):
    secret: str
    uri: str


def _issue(svc: Services, response: Response, user: User) -> TokenOut:
    secret = svc.settings.jwt_secret.get_secret_value()
    response.set_cookie(
        COOKIE,
        make_token(secret, user.id, user.email, "refresh"),
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=svc.settings.env != "dev",  # plain http only for local development
        samesite="strict",
        path="/api/v1/auth",
    )
    return TokenOut(
        access_token=make_token(secret, user.id, user.email, "access"),
        expires_in=900,
        email=user.email,
    )


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, request: Request, response: Response, svc: Svc, db: Db) -> TokenOut:
    ip = client_ip(request) or "?"
    key = f"{ip}|{body.email.lower()}"
    if svc.limiter.blocked(key):
        raise HTTPException(
            429, "too many attempts", headers={"Retry-After": str(svc.limiter.retry_after(key))}
        )
    user = (
        await db.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    pw_ok = verify_password(user.password_hash if user else _DUMMY_HASH, body.password)
    ok = False
    if user and pw_ok and user.totp_secret_enc:
        try:
            secret = (
                svc.get_cipher()
                .decrypt(user.totp_secret_enc, aad=f"user:{user.id}:totp".encode())
                .decode()
            )
        except CryptoError as e:
            raise HTTPException(503, "encryption is not configured") from e
        ok = svc.totp.verify(str(user.id), secret, body.totp)
    if not (user and ok):
        svc.limiter.fail(key)
        audit(
            db, user.id if user else None, "auth.login_failed", f"user:{body.email.lower()}", ip=ip
        )
        await db.commit()
        raise HTTPException(401, "invalid credentials")  # never say which factor was wrong
    svc.limiter.clear(key)
    audit(db, user.id, "auth.login", f"user:{user.id}", ip=ip)
    await db.commit()
    return _issue(svc, response, user)


@router.post("/refresh", response_model=TokenOut)
async def refresh(request: Request, response: Response, svc: Svc, db: Db) -> TokenOut:
    raw = request.cookies.get(COOKIE)
    if not raw:
        raise HTTPException(401, "no session")
    try:
        claims = read_token(svc.settings.jwt_secret.get_secret_value(), raw, "refresh")
    except TokenError as e:
        raise HTTPException(401, "session expired") from e
    user = await db.get(User, claims.user_id)
    if user is None:
        raise HTTPException(401, "session expired")
    return _issue(svc, response, user)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/api/v1/auth")


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser) -> MeOut:
    return MeOut(id=str(user.user_id), email=user.email)


@router.post("/totp/setup", response_model=TotpSetupOut)
async def totp_setup(user: TotpUser, request: Request, svc: Svc, db: Db) -> TotpSetupOut:
    """Rotate the TOTP secret. Needs a valid current code (a stolen access token is not enough)."""
    row = await db.get(User, user.user_id)
    assert row is not None
    secret = new_totp_secret()
    row.totp_secret_enc = svc.get_cipher().encrypt(
        secret.encode(), aad=f"user:{row.id}:totp".encode()
    )
    svc.totp.reset(str(row.id))
    audit(db, row.id, "auth.totp_rotated", f"user:{row.id}", ip=client_ip(request))
    await db.commit()
    return TotpSetupOut(secret=secret, uri=totp_uri(secret, row.email))


async def create_user(svc: Services, email: str, password: str) -> tuple[User, str]:
    """Used by the CLI: there is no open registration. Returns the user and its new TOTP secret."""
    assert svc.db is not None
    secret = new_totp_secret()
    async with svc.db() as db:
        user = User(email=email.lower(), password_hash=hash_password(password))
        db.add(user)
        await db.flush()
        user.totp_secret_enc = svc.get_cipher().encrypt(
            secret.encode(), aad=f"user:{user.id}:totp".encode()
        )
        audit(db, user.id, "auth.user_created", f"user:{user.id}")
        await db.commit()
    return user, secret
