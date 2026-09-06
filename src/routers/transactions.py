import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_current_user
from ..db import get_db
from ..models.category import Category
from ..models.transaction import Transaction
from ..models.user import User
from ..schemas.transaction import TransactionCreate, TransactionRead, TransactionUpdate
from ..utils.pagination import PaginatedResponse, PaginationParams, paginate

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _get_owned_transaction(transaction_id: uuid.UUID, user: User, db: Session) -> Transaction:
    transaction = (
        db.query(Transaction)
        .filter(Transaction.id == transaction_id, Transaction.user_id == user.id)
        .first()
    )
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


def _validate_category(category_id: uuid.UUID, user: User, db: Session) -> None:
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user.id)
        .first()
    )
    if not category:
        raise HTTPException(status_code=400, detail="Category not found")


@router.get("", response_model=PaginatedResponse[TransactionRead])
def list_transactions(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    category_id: uuid.UUID | None = None,
    pagination: PaginationParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Transaction).filter(Transaction.user_id == user.id)
    if from_ is not None:
        query = query.filter(Transaction.transaction_date >= from_)
    if to is not None:
        query = query.filter(Transaction.transaction_date <= to)
    if category_id is not None:
        query = query.filter(Transaction.category_id == category_id)
    query = query.order_by(
        Transaction.transaction_date.desc(),
        Transaction.created_at.desc(),
        Transaction.id.desc(),
    )
    return paginate(query, pagination)


@router.post("", response_model=TransactionRead, status_code=201)
def create_transaction(
    payload: TransactionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_category(payload.category_id, user, db)

    transaction = Transaction(
        id=uuid.uuid4(),
        amount=payload.amount,
        description=payload.description,
        category_id=payload.category_id,
        account_type=payload.account_type,
        transaction_date=payload.transaction_date,
        user_id=user.id,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction(
    transaction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _get_owned_transaction(transaction_id, user, db)


@router.put("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = _get_owned_transaction(transaction_id, user, db)

    update_data = payload.model_dump(exclude_unset=True)
    if "category_id" in update_data:
        _validate_category(update_data["category_id"], user, db)

    for field, value in update_data.items():
        setattr(transaction, field, value)

    db.commit()
    db.refresh(transaction)
    return transaction


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(
    transaction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = _get_owned_transaction(transaction_id, user, db)
    db.delete(transaction)
    db.commit()
