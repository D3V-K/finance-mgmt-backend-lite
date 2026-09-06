import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..dependencies import get_current_user
from ..db import get_db
from ..models.enums import AccountType
from ..models.opening_balance import AccountOpeningBalance
from ..models.user import User
from ..schemas.opening_balance import OpeningBalanceRead, OpeningBalanceUpsert

router = APIRouter(prefix="/opening-balances", tags=["opening-balances"])


@router.get("", response_model=list[OpeningBalanceRead])
def list_opening_balances(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(AccountOpeningBalance)
        .filter(AccountOpeningBalance.user_id == user.id)
        .order_by(AccountOpeningBalance.account_type.asc())
        .all()
    )


@router.put("/{account_type}", response_model=OpeningBalanceRead)
def upsert_opening_balance(
    account_type: AccountType,
    payload: OpeningBalanceUpsert,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    opening_balance = (
        db.query(AccountOpeningBalance)
        .filter(
            AccountOpeningBalance.user_id == user.id,
            AccountOpeningBalance.account_type == account_type,
        )
        .first()
    )

    if opening_balance is None:
        opening_balance = AccountOpeningBalance(
            id=uuid.uuid4(),
            user_id=user.id,
            account_type=account_type,
            amount=payload.amount,
            as_of_date=payload.as_of_date,
        )
        db.add(opening_balance)
    else:
        opening_balance.amount = payload.amount
        opening_balance.as_of_date = payload.as_of_date

    db.commit()
    db.refresh(opening_balance)
    return opening_balance
