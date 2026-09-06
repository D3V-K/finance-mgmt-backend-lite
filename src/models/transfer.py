import uuid

from .base import Base
from .enums import AccountType
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, CheckConstraint, Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime

class Transfer(Base):
    __tablename__ = "transfers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    from_account = Column(SqlEnum(AccountType), nullable=False)
    to_account = Column(SqlEnum(AccountType), nullable=False)
    amount = Column(Integer, nullable=False)
    transfer_date = Column(Date, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        CheckConstraint("from_account <> to_account", name="ck_transfer_distinct_accounts"),
        CheckConstraint("amount > 0", name="ck_transfer_amount_positive"),
    )
