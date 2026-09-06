"""add account_type to transactions

Revision ID: f012a498e312
Revises: ef190ad2ea48
Create Date: 2026-09-06 19:51:20.355363

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f012a498e312'
down_revision: Union[str, Sequence[str], None] = 'ef190ad2ea48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    account_type = sa.Enum("CASH", "BANK", name="accounttype")
    account_type.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "transactions",
        sa.Column("account_type", account_type, nullable=True),
    )
    op.execute("UPDATE transactions SET account_type = 'CASH' WHERE account_type IS NULL")
    op.alter_column("transactions", "account_type", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("transactions", "account_type")
    sa.Enum(name="accounttype").drop(op.get_bind(), checkfirst=True)
