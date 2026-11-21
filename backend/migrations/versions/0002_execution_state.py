"""execution state on positions (manual positions have no bot)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-21 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("positions", "bot_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("positions", sa.Column("entry_cid", sa.String(length=64), nullable=True))
    op.add_column(
        "positions", sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.create_unique_constraint("positions_entry_cid_key", "positions", ["entry_cid"])


def downgrade() -> None:
    op.drop_constraint("positions_entry_cid_key", "positions", type_="unique")
    op.drop_column("positions", "state")
    op.drop_column("positions", "entry_cid")
    op.execute("DELETE FROM trades WHERE position_id IN (SELECT id FROM positions WHERE bot_id IS NULL)")
    op.execute("DELETE FROM positions WHERE bot_id IS NULL")
    op.alter_column("positions", "bot_id", existing_type=sa.UUID(), nullable=False)
