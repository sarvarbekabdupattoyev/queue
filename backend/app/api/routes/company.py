import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, OwnCompany, require_roles
from app.core.config import get_settings
from app.models import Company, CompanyLocation, CompanyPhone, User, UserRole
from app.schemas.company import (
    CompanyCreate,
    CompanyLocationCreate,
    CompanyLocationOut,
    CompanyOut,
    CompanyPhoneCreate,
    CompanyPhoneOut,
    CompanyUpdate,
)
from app.services.errors import DomainError
from app.services.telegram.manager import bot_manager

router = APIRouter(prefix="/company", tags=["company"])

OwnerOnly = Depends(require_roles(UserRole.OWNER))

ALLOWED_LOGO_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


async def _company_out(db: DbSession, company: Company) -> CompanyOut:
    loaded = await db.scalar(
        select(Company)
        .where(Company.id == company.id)
        .options(selectinload(Company.phones), selectinload(Company.locations))
    )
    return CompanyOut(
        id=loaded.id,
        name=loaded.name,
        logo_url=f"/media/{loaded.logo_path}" if loaded.logo_path else None,
        telegram_bot_username=loaded.telegram_bot_username,
        has_bot_token=bool(loaded.telegram_bot_token),
        phones=[CompanyPhoneOut.model_validate(p) for p in loaded.phones],
        locations=[CompanyLocationOut.model_validate(loc) for loc in loaded.locations],
    )


@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED, dependencies=[OwnerOnly])
async def create_company(payload: CompanyCreate, db: DbSession, user: CurrentUser) -> CompanyOut:
    if user.company_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sizda allaqachon kompaniya bor")
    company = Company(name=payload.name.strip(), owner_id=user.id)
    db.add(company)
    await db.flush()
    user.company_id = company.id
    await db.commit()
    return await _company_out(db, company)


@router.get("", response_model=CompanyOut)
async def get_company(db: DbSession, company: OwnCompany) -> CompanyOut:
    return await _company_out(db, company)


@router.patch("", response_model=CompanyOut, dependencies=[OwnerOnly])
async def update_company(payload: CompanyUpdate, db: DbSession, company: OwnCompany) -> CompanyOut:
    if payload.name is not None:
        company.name = payload.name.strip()
    if payload.telegram_bot_token is not None:
        token = payload.telegram_bot_token.strip() or None
        try:
            username = await bot_manager.set_token(company.id, token)
        except DomainError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from None
        company.telegram_bot_token = token
        company.telegram_bot_username = username
    await db.commit()
    return await _company_out(db, company)


@router.post("/logo", response_model=CompanyOut, dependencies=[OwnerOnly])
async def upload_logo(file: UploadFile, db: DbSession, company: OwnCompany) -> CompanyOut:
    settings = get_settings()
    extension = ALLOWED_LOGO_TYPES.get(file.content_type or "")
    if extension is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Logo PNG, JPEG, WebP yoki SVG formatida bo'lishi kerak"
        )
    content = await file.read()
    if len(content) > settings.max_logo_size:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Logo hajmi 2 MB dan oshmasin")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    if company.logo_path:
        old = settings.upload_dir / company.logo_path
        old.unlink(missing_ok=True)
    filename = f"logo-{company.id}-{secrets.token_hex(4)}{extension}"
    (settings.upload_dir / filename).write_bytes(content)
    company.logo_path = filename
    await db.commit()
    return await _company_out(db, company)


@router.post("/phones", response_model=CompanyPhoneOut, status_code=status.HTTP_201_CREATED, dependencies=[OwnerOnly])
async def add_phone(payload: CompanyPhoneCreate, db: DbSession, company: OwnCompany) -> CompanyPhoneOut:
    phone = CompanyPhone(company_id=company.id, phone=payload.phone, label=payload.label.strip())
    db.add(phone)
    await db.commit()
    await db.refresh(phone)
    return CompanyPhoneOut.model_validate(phone)


@router.delete("/phones/{phone_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[OwnerOnly])
async def delete_phone(phone_id: int, db: DbSession, company: OwnCompany) -> None:
    phone = await db.get(CompanyPhone, phone_id)
    if phone is None or phone.company_id != company.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Raqam topilmadi")
    await db.delete(phone)
    await db.commit()


@router.post("/locations", response_model=CompanyLocationOut, status_code=status.HTTP_201_CREATED, dependencies=[OwnerOnly])
async def add_location(payload: CompanyLocationCreate, db: DbSession, company: OwnCompany) -> CompanyLocationOut:
    location = CompanyLocation(
        company_id=company.id,
        name=payload.name.strip(),
        address=payload.address.strip(),
        map_url=payload.map_url.strip(),
    )
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return CompanyLocationOut.model_validate(location)


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[OwnerOnly])
async def delete_location(location_id: int, db: DbSession, company: OwnCompany) -> None:
    location = await db.get(CompanyLocation, location_id)
    if location is None or location.company_id != company.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Manzil topilmadi")
    await db.delete(location)
    await db.commit()
