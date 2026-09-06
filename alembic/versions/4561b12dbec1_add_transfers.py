"""add transfers

Revision ID: 4561b12dbec1
Revises: ac64c0372a8b
Create Date: 2026-09-06 20:03:28.889217

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4561b12dbec1'
down_revision: Union[str, Sequence[str], None] = 'ac64c0372a8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('transfers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('from_account', postgresql.ENUM('CASH', 'BANK', name='accounttype', create_type=False), nullable=False),
    sa.Column('to_account', postgresql.ENUM('CASH', 'BANK', name='accounttype', create_type=False), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('transfer_date', sa.Date(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('from_account <> to_account', name='ck_transfer_distinct_accounts'),
    sa.CheckConstraint('amount > 0', name='ck_transfer_amount_positive'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('transfers')
