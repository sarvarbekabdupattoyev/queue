from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession, OwnCompany, require_roles
from app.models import Desk, User, UserRole
from app.schemas.staff import DeskCreate, DeskOut, DeskUpdate

router = APIRouter(prefix="/desks", tags=["desks"])

OwnerOnly = Depends(require_roles(UserRole.OWNER))
AnyStaff = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER, UserRole.SCANNER))


async def _desk_out(db: DbSession, desk: Desk) -> DeskOut:
    manager_name = None
    if desk.manager_id is not None:
        manager = await db.get(User, desk.manager_id)
        manager_name = manager.full_name if manager else None
    out = DeskOut.model_validate(desk)
    out.manager_name = manager_name
    return out


async def _validate_manager(db: DbSession, company_id: int, manager_id: int) -> None:
    manager = await db.get(User, manager_id)
    if manager is None or manager.company_id != company_id or manager.role != UserRole.MANAGER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Menejer topilmadi")


@router.get("", response_model=list[DeskOut], dependencies=[AnyStaff])
async def list_desks(db: DbSession, company: OwnCompany) -> list[DeskOut]:
    desks = (
        await db.scalars(select(Desk).where(Desk.company_id == company.id).order_by(Desk.number))
    ).all()
    return [await _desk_out(db, d) for d in desks]


@router.post("", response_model=DeskOut, status_code=status.HTTP_201_CREATED, dependencies=[OwnerOnly])
async def create_desk(payload: DeskCreate, db: DbSession, company: OwnCompany) -> DeskOut:
    if payload.manager_id is not None:
        await _validate_manager(db, company.id, payload.manager_id)
    desk = Desk(
        company_id=company.id,
        number=payload.number,
        name=payload.name.strip(),
        manager_id=payload.manager_id,
    )
    db.add(desk)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu raqamli stol allaqachon bor") from None
    await db.refresh(desk)
    return await _desk_out(db, desk)


@router.patch("/{desk_id}", response_model=DeskOut, dependencies=[OwnerOnly])
async def update_desk(
    desk_id: int, payload: DeskUpdate, db: DbSession, company: OwnCompany
) -> DeskOut:
    desk = await db.get(Desk, desk_id)
    if desk is None or desk.company_id != company.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stol topilmadi")
    if payload.number is not None:
        desk.number = payload.number
    if payload.name is not None:
        desk.name = payload.name.strip()
    if payload.clear_manager:
        desk.manager_id = None
    elif payload.manager_id is not None:
        await _validate_manager(db, company.id, payload.manager_id)
        desk.manager_id = payload.manager_id
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu raqamli stol allaqachon bor") from None
    await db.refresh(desk)
    return await _desk_out(db, desk)


@router.delete("/{desk_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[OwnerOnly])
async def delete_desk(desk_id: int, db: DbSession, company: OwnCompany) -> None:
    desk = await db.get(Desk, desk_id)
    if desk is None or desk.company_id != company.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stol topilmadi")
    await db.delete(desk)
    await db.commit()
