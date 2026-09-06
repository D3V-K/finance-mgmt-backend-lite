import uuid

from .base import Base
from .enums import AccountType
from sqlalchemy import Column, Integer, DateTime, Date, ForeignKey, UniqueConstraint, Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime

class AccountOpeningBalance(Base):
    __tablename__ = "account_opening_balances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_type = Column(SqlEnum(AccountType), nullable=False)
    amount = Column(Integer, nullable=False)
    as_of_date = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("user_id", "account_type", name="uq_opening_balance_user_account"),
    )
