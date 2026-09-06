"""add account opening balances

Revision ID: ac64c0372a8b
Revises: f012a498e312
Create Date: 2026-09-06 19:57:06.670443

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ac64c0372a8b'
down_revision: Union[str, Sequence[str], None] = 'f012a498e312'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('account_opening_balances',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('account_type', postgresql.ENUM('CASH', 'BANK', name='accounttype', create_type=False), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('as_of_date', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'account_type', name='uq_opening_balance_user_account')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('account_opening_balances')
