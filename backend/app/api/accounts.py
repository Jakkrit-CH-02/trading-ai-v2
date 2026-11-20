"""Exchange accounts (SPEC 12): keys are verified BEFORE being stored and refused if they can
withdraw. Secrets are envelope-encrypted; responses only ever show the last 4 characters."""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.api.schemas_bots import AccountIn, AccountOut
from app.api.services import AccountProbe, Services, get_services
from app.auth.audit import audit
from app.auth.crypto import CryptoError
from app.auth.deps import CurrentUser, Db, TotpUser, client_ip, current_user
from app.core.models import ExchangeAccount
from app.exchange.binance_testnet import ENVIRONMENTS, BinanceTestnetAdapter
from app.exchange.errors import ExchangeError

router = APIRouter(
    prefix="/api/v1/accounts", dependencies=[Depends(current_user)], tags=["accounts"]
)
Svc = Annotated[Services, Depends(get_services)]


def assess_permissions(info: dict[str, Any]) -> list[str]:
    """Reasons a key must be rejected. Withdrawal rights are never acceptable (SPEC 12)."""
    problems = []
    if info.get("canWithdraw"):
        problems.append(
            "key can withdraw funds: disable Withdrawals and Universal Transfer on Binance"
        )
    if not info.get("canTrade"):
        problems.append("key cannot trade: enable Spot & Margin Trading")
    return problems


def default_factory(settings_env: str) -> Any:
    def make(key: str, secret: str, is_testnet: bool) -> AccountProbe:
        if not is_testnet:  # the adapter refuses real hosts anyway (LiveTradingForbidden)
            raise HTTPException(403, "live accounts are disabled until Gate B")
        return BinanceTestnetAdapter(key, secret, base_url=ENVIRONMENTS[settings_env])

    return make


async def probe(svc: Services, key: str, secret: str, is_testnet: bool) -> list[str]:
    if not is_testnet and svc.settings.binance_testnet_only:
        raise HTTPException(403, "live accounts are disabled until Gate B (BINANCE_TESTNET_ONLY)")
    factory = svc.adapter_factory or default_factory(svc.settings.binance_trading_env)
    adapter = factory(key, secret, is_testnet)
    try:
        return assess_permissions(await adapter.account_info())
    except ExchangeError as e:
        raise HTTPException(422, f"could not verify the key: {type(e).__name__}") from e
    finally:
        await adapter.aclose()


def last4(svc: Services, row: ExchangeAccount) -> str:
    try:
        return (
            svc.get_cipher()
            .decrypt(row.api_key_enc, aad=f"account:{row.id}:key".encode())
            .decode()[-4:]
        )
    except CryptoError:
        return "????"


def out(svc: Services, row: ExchangeAccount) -> AccountOut:
    return AccountOut(
        id=row.id,
        label=row.label,
        exchange=row.exchange,
        key_type=row.key_type,
        is_testnet=row.is_testnet,
        api_key_last4=last4(svc, row),
        permissions_checked_at=row.permissions_checked_at,
    )


@router.get("", response_model=list[AccountOut])
async def list_accounts(svc: Svc, db: Db) -> list[AccountOut]:
    rows = (
        await db.execute(select(ExchangeAccount).order_by(ExchangeAccount.created_at))
    ).scalars()
    return [out(svc, r) for r in rows]


@router.post("", response_model=AccountOut, status_code=201)
async def add_account(
    body: AccountIn, user: TotpUser, request: Request, svc: Svc, db: Db
) -> AccountOut:
    problems = await probe(svc, body.api_key, body.api_secret, body.is_testnet)
    if problems:
        audit(
            db,
            user.user_id,
            "account.rejected",
            f"account:{body.label}",
            after={"problems": problems},
            ip=client_ip(request),
        )
        await db.commit()
        raise HTTPException(422, {"message": "API key rejected", "problems": problems})
    try:
        cipher = svc.get_cipher()
    except CryptoError as e:
        raise HTTPException(503, "encryption is not configured") from e
    row = ExchangeAccount(
        user_id=user.user_id,
        label=body.label,
        key_type=body.key_type,
        is_testnet=body.is_testnet,
        api_key_enc=b"",
        api_secret_enc=b"",
        permissions_checked_at=datetime.now(UTC),
    )
    db.add(row)
    await db.flush()  # the record id is part of the encryption context (aad)
    row.api_key_enc = cipher.encrypt(body.api_key.encode(), aad=f"account:{row.id}:key".encode())
    row.api_secret_enc = cipher.encrypt(
        body.api_secret.encode(), aad=f"account:{row.id}:secret".encode()
    )
    audit(
        db,
        user.user_id,
        "account.add",
        f"account:{row.id}",
        after={"label": body.label, "is_testnet": body.is_testnet, "key_type": body.key_type},
        ip=client_ip(request),
    )
    await db.commit()
    await svc.notifier.send(f"API key added: {body.label}")
    return out(svc, row)


@router.post("/{account_id}/verify", response_model=AccountOut)
async def verify_account(
    account_id: UUID, user: CurrentUser, request: Request, svc: Svc, db: Db
) -> AccountOut:
    row = await db.get(ExchangeAccount, account_id)
    if row is None:
        raise HTTPException(404, "account not found")
    try:
        c = svc.get_cipher()
        key = c.decrypt(row.api_key_enc, aad=f"account:{row.id}:key".encode()).decode()
        secret = c.decrypt(row.api_secret_enc, aad=f"account:{row.id}:secret".encode()).decode()
    except CryptoError as e:
        raise HTTPException(503, "cannot decrypt the stored key") from e
    problems = await probe(svc, key, secret, row.is_testnet)
    if problems:
        row.permissions_checked_at = None  # a key that no longer verifies must not run bots
        audit(
            db,
            user.user_id,
            "account.verify_failed",
            f"account:{row.id}",
            after={"problems": problems},
            ip=client_ip(request),
        )
        await db.commit()
        raise HTTPException(422, {"message": "API key rejected", "problems": problems})
    row.permissions_checked_at = datetime.now(UTC)
    audit(db, user.user_id, "account.verify", f"account:{row.id}", ip=client_ip(request))
    await db.commit()
    return out(svc, row)
