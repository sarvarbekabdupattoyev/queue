from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession, OwnCompany, require_roles
from app.models import Branch, UserRole
from app.schemas.branch import BranchCreate, BranchOut, BranchUpdate

router = APIRouter(prefix="/branches", tags=["branches"])

OwnerOnly = Depends(require_roles(UserRole.OWNER))
AnyStaff = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER, UserRole.SCANNER))


async def _own_branch(db: DbSession, company_id: int, branch_id: int) -> Branch:
    branch = await db.get(Branch, branch_id)
    if branch is None or branch.company_id != company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filial topilmadi")
    return branch


@router.get("", response_model=list[BranchOut], dependencies=[AnyStaff])
async def list_branches(db: DbSession, company: OwnCompany) -> list[BranchOut]:
    branches = (
        await db.scalars(
            select(Branch).where(Branch.company_id == company.id).order_by(Branch.name)
        )
    ).all()
    return [BranchOut.model_validate(b) for b in branches]


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
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu nomli filial allaqachon bor") from None
    await db.refresh(branch)
    return BranchOut.model_validate(branch)


@router.patch("/{branch_id}", response_model=BranchOut, dependencies=[OwnerOnly])
async def update_branch(
    branch_id: int, payload: BranchUpdate, db: DbSession, company: OwnCompany
) -> BranchOut:
    branch = await _own_branch(db, company.id, branch_id)
    if payload.name is not None:
        branch.name = payload.name.strip()
    if payload.address is not None:
        branch.address = payload.address.strip()
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu nomli filial allaqachon bor") from None
    await db.refresh(branch)
    return BranchOut.model_validate(branch)


@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[OwnerOnly])
async def delete_branch(branch_id: int, db: DbSession, company: OwnCompany) -> None:
    """Events keep running when their branch is removed — branch_id falls back
    to NULL (branches are optional by design)."""
    branch = await _own_branch(db, company.id, branch_id)
    await db.delete(branch)
    await db.commit()
