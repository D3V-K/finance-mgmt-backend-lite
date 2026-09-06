import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models.enums import AccountType


class TransferCreate(BaseModel):
    from_account: AccountType
    to_account: AccountType
    amount: int = Field(gt=0)
    transfer_date: date
    description: str | None = None

    @model_validator(mode="after")
    def _distinct_accounts(self) -> "TransferCreate":
        if self.from_account == self.to_account:
            raise ValueError("from_account and to_account must differ")
        return self


class TransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_account: AccountType
    to_account: AccountType
    amount: int
    transfer_date: date
    description: str | None = None
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
