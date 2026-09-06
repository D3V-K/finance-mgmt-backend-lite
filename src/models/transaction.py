from .base import Base
from .enums import AccountType
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Index, Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    amount = Column(Integer, nullable=False)
    description = Column(String, nullable=True)
    date = Column(DateTime, nullable=False, default=datetime.now)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    account_type = Column(SqlEnum(AccountType), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    transaction_date = Column(Date, nullable=False, default=datetime.now().date())

    __table_args__ = (
        Index("idx_transactions_user_id_tx_date", "user_id", "transaction_date"),
        Index("idx_category_id", "category_id"),
    )

