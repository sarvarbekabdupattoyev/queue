from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession, OwnCompany, require_roles
from app.models import Branch, Desk, SaleEvent, User, UserRole, event_branches
from app.schemas.branch import BranchCreate, BranchOut, BranchUpdate

router = APIRouter(prefix="/branches", tags=["branches"])

OwnerOnly = Depends(require_roles(UserRole.OWNER))
AnyStaff = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER, UserRole.SCANNER))


async def _get_branch(db: DbSession, company_id: int, branch_id: int) -> Branch:
    branch = await db.get(Branch, branch_id)
    if branch is None or branch.company_id != company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filial topilmadi")
    return branch


@router.get("", response_model=list[BranchOut], dependencies=[AnyStaff])
async def list_branches(db: DbSession, company: OwnCompany) -> list[BranchOut]:
    branches = (
        await db.scalars(
            select(Branch).where(Branch.company_id == company.id).order_by(Branch.id)
        )
    ).all()
    desk_counts = dict(
        (
            await db.execute(
                select(Desk.branch_id, func.count())
                .where(Desk.company_id == company.id, Desk.branch_id.is_not(None))
                .group_by(Desk.branch_id)
            )
        ).all()
    )
    employee_counts = dict(
        (
            await db.execute(
                select(User.branch_id, func.count())
                .where(User.company_id == company.id, User.branch_id.is_not(None))
                .group_by(User.branch_id)
            )
        ).all()
    )
    out = []
    for branch in branches:
        item = BranchOut.model_validate(branch)
        item.desk_count = desk_counts.get(branch.id, 0)
        item.employee_count = employee_counts.get(branch.id, 0)
        out.append(item)
    return out


@router.post("", response_model=BranchOut, status_code=status.HTTP_201_CREATED, dependencies=[OwnerOnly])
async def create_branch(payload: BranchCreate, db: DbSession, company: OwnCompany) -> BranchOut:
    branch = Branch(
        company_id=company.id, name=payload.name.strip(), address=payload.address.strip()
    )
    db.add(branch)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu nomdagi filial allaqachon bor") from None
    await db.refresh(branch)
    return BranchOut.model_validate(branch)


@router.patch("/{branch_id}", response_model=BranchOut, dependencies=[OwnerOnly])
async def update_branch(
    branch_id: int, payload: BranchUpdate, db: DbSession, company: OwnCompany
) -> BranchOut:
    branch = await _get_branch(db, company.id, branch_id)
    if payload.name is not None:
        branch.name = payload.name.strip()
    if payload.address is not None:
        branch.address = payload.address.strip()
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu nomdagi filial allaqachon bor") from None
    await db.refresh(branch)
    return BranchOut.model_validate(branch)


@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[OwnerOnly])
async def delete_branch(branch_id: int, db: DbSession, company: OwnCompany) -> None:
    branch = await _get_branch(db, company.id, branch_id)
    # a branch wired into an active event still owns a slice of the queue —
    # deleting it would strand those tickets
    active_event = await db.scalar(
        select(SaleEvent.id)
        .join(event_branches, event_branches.c.event_id == SaleEvent.id)
        .where(event_branches.c.branch_id == branch.id, SaleEvent.is_active.is_(True))
        .limit(1)
    )
    if active_event is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Bu filial faol tadbirga ulangan — avval tadbirni yoping yoki filialni tadbirdan chiqaring",
        )
    await db.delete(branch)
    await db.commit()
