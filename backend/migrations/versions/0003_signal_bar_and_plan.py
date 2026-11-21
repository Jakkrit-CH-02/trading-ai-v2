"""signals: bar_time (idempotency), exit plan and reasons

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-21 00:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("bar_time", sa.DateTime(timezone=True), nullable=True))
    for name in ("exit_plan", "reasons"):
        op.add_column(
            "signals", sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), nullable=True)
        )
    op.create_unique_constraint(
        "uq_signal_bar", "signals", ["bot_id", "symbol", "strategy", "bar_time"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_signal_bar", "signals", type_="unique")
    for name in ("reasons", "exit_plan", "bar_time"):
        op.drop_column("signals", name)
