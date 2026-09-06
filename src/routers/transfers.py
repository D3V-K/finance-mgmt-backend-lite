import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_current_user
from ..db import get_db
from ..models.transfer import Transfer
from ..models.user import User
from ..schemas.transfer import TransferCreate, TransferRead
from ..utils.pagination import PaginatedResponse, PaginationParams, paginate

router = APIRouter(prefix="/transfers", tags=["transfers"])


def _get_owned_transfer(transfer_id: uuid.UUID, user: User, db: Session) -> Transfer:
    transfer = (
        db.query(Transfer)
        .filter(Transfer.id == transfer_id, Transfer.user_id == user.id)
        .first()
    )
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return transfer


@router.get("", response_model=PaginatedResponse[TransferRead])
def list_transfers(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    pagination: PaginationParams = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Transfer).filter(Transfer.user_id == user.id)
    if from_ is not None:
        query = query.filter(Transfer.transfer_date >= from_)
    if to is not None:
        query = query.filter(Transfer.transfer_date <= to)
    query = query.order_by(
        Transfer.transfer_date.desc(),
        Transfer.created_at.desc(),
        Transfer.id.desc(),
    )
    return paginate(query, pagination)


@router.post("", response_model=TransferRead, status_code=201)
def create_transfer(
    payload: TransferCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transfer = Transfer(
        id=uuid.uuid4(),
        from_account=payload.from_account,
        to_account=payload.to_account,
        amount=payload.amount,
        transfer_date=payload.transfer_date,
        description=payload.description,
        user_id=user.id,
    )
    db.add(transfer)
    db.commit()
    db.refresh(transfer)
    return transfer


@router.get("/{transfer_id}", response_model=TransferRead)
def get_transfer(
    transfer_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _get_owned_transfer(transfer_id, user, db)


@router.delete("/{transfer_id}", status_code=204)
def delete_transfer(
    transfer_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transfer = _get_owned_transfer(transfer_id, user, db)
    db.delete(transfer)
    db.commit()
