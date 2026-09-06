import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from ..models.enums import AccountType


class OpeningBalanceUpsert(BaseModel):
    amount: int
    as_of_date: date


class OpeningBalanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    account_type: AccountType
    amount: int
    as_of_date: date
    created_at: datetime
    updated_at: datetime
