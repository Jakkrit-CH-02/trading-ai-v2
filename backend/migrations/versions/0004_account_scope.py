"""orders/positions know their exchange account (several accounts, one reconciler each)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21 01:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("orders", "positions"):
        op.add_column(table, sa.Column("account_id", sa.UUID(), nullable=True))
        op.create_foreign_key(f"{table}_account_id_fkey", table, "exchange_accounts", ["account_id"], ["id"])


def downgrade() -> None:
    for table in ("positions", "orders"):
        op.drop_constraint(f"{table}_account_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "account_id")
