from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, OwnCompany, require_roles
from app.core.security import generate_password, hash_password_async
from app.models import Branch, User, UserRole
from app.schemas.auth import UserOut
from app.schemas.staff import EmployeeCreate, EmployeeUpdate, EmployeeWithPassword

router = APIRouter(
    prefix="/employees", tags=["employees"], dependencies=[Depends(require_roles(UserRole.OWNER))]
)

EMPLOYEE_ROLES = (UserRole.MANAGER, UserRole.SCANNER)


async def _validate_branch(db: DbSession, company_id: int, branch_id: int) -> None:
    branch = await db.get(Branch, branch_id)
    if branch is None or branch.company_id != company_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Filial topilmadi")


async def _get_employee(db: DbSession, company_id: int, employee_id: int) -> User:
    employee = await db.get(User, employee_id)
    if (
        employee is None
        or employee.company_id != company_id
        or employee.role not in EMPLOYEE_ROLES
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    return employee


@router.get("", response_model=list[UserOut])
async def list_employees(db: DbSession, company: OwnCompany) -> list[UserOut]:
    employees = (
        await db.scalars(
            select(User)
            .where(User.company_id == company.id, User.role.in_(EMPLOYEE_ROLES))
            .order_by(User.created_at)
        )
    ).all()
    return [UserOut.model_validate(e) for e in employees]


@router.post("", response_model=EmployeeWithPassword, status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: EmployeeCreate, db: DbSession, company: OwnCompany
) -> EmployeeWithPassword:
    if payload.role not in EMPLOYEE_ROLES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Xodim roli faqat 'manager' yoki 'scanner' bo'ladi"
        )
    if payload.branch_id is not None:
        await _validate_branch(db, company.id, payload.branch_id)
    # a phone is unique inside THIS company only — another company employing
    # the same person (same phone) must not block hiring them here
    company_id = company.id
    existing = await db.scalar(
        select(User.id).where(User.phone == payload.phone, User.company_id == company_id)
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Bu raqam kompaniyangizda allaqachon ro'yxatdan o'tgan"
        )
    password = generate_password()
    employee = User(
        phone=payload.phone,
        password_hash=await hash_password_async(password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        role=payload.role,
        company_id=company_id,
        branch_id=payload.branch_id,
    )
    db.add(employee)
    try:
        await db.commit()
    except IntegrityError:
        # lost a race adding the same phone to this company twice
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Bu raqam kompaniyangizda allaqachon ro'yxatdan o'tgan"
        ) from None
    await db.refresh(employee)
    # The plain password is returned exactly once; only the hash is stored.
    return EmployeeWithPassword(employee=UserOut.model_validate(employee), password=password)


@router.patch("/{employee_id}", response_model=UserOut)
async def update_employee(
    employee_id: int, payload: EmployeeUpdate, db: DbSession, company: OwnCompany
) -> UserOut:
    company_id = company.id
    employee = await _get_employee(db, company_id, employee_id)
    if payload.role is not None:
        if payload.role not in EMPLOYEE_ROLES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Xodim roli faqat 'manager' yoki 'scanner' bo'ladi"
            )
        employee.role = payload.role
    if payload.first_name is not None:
        employee.first_name = payload.first_name.strip()
    if payload.last_name is not None:
        employee.last_name = payload.last_name.strip()
    if payload.phone is not None and payload.phone != employee.phone:
        taken = await db.scalar(
            select(User.id).where(
                User.phone == payload.phone,
                User.company_id == company_id,
                User.id != employee.id,
            )
        )
        if taken is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Bu raqam kompaniyangizda allaqachon ro'yxatdan o'tgan"
            )
        employee.phone = payload.phone
    if payload.is_active is not None:
        employee.is_active = payload.is_active
    if payload.clear_branch:
        employee.branch_id = None
    elif payload.branch_id is not None:
        await _validate_branch(db, company_id, payload.branch_id)
        employee.branch_id = payload.branch_id
    try:
        await db.commit()
    except IntegrityError:
        # lost a race with another edit adding the same phone to this company
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Bu raqam kompaniyangizda allaqachon ro'yxatdan o'tgan"
        ) from None
    await db.refresh(employee)
    return UserOut.model_validate(employee)


@router.post("/{employee_id}/reset-password", response_model=EmployeeWithPassword)
async def reset_password(
    employee_id: int, db: DbSession, company: OwnCompany
) -> EmployeeWithPassword:
    employee = await _get_employee(db, company.id, employee_id)
    password = generate_password()
    employee.password_hash = await hash_password_async(password)
    await db.commit()
    return EmployeeWithPassword(employee=UserOut.model_validate(employee), password=password)


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(employee_id: int, db: DbSession, company: OwnCompany) -> None:
    employee = await _get_employee(db, company.id, employee_id)
    await db.delete(employee)
    await db.commit()
