import asyncio
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, OwnCompany, require_roles
from app.core.config import get_settings
from app.models import (
    MAX_BOTS_PER_COMPANY,
    Company,
    CompanyBot,
    CompanyLocation,
    CompanyPhone,
    UserRole,
)
from app.schemas.company import (
    CompanyBotCreate,
    CompanyBotOut,
    CompanyCreate,
    CompanyLocationCreate,
    CompanyLocationOut,
    CompanyOut,
    CompanyPhoneCreate,
    CompanyPhoneOut,
    CompanyUpdate,
)
from app.services.errors import DomainError
from app.services.notify import notify_bot_token_changed
from app.services.telegram.manager import bot_manager, validate_token

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
        .options(
            selectinload(Company.phones),
            selectinload(Company.locations),
            selectinload(Company.bots),
        )
    )
    bots = [CompanyBotOut.model_validate(b) for b in loaded.bots]
    return CompanyOut(
        id=loaded.id,
        name=loaded.name,
        logo_url=f"/media/{loaded.logo_path}" if loaded.logo_path else None,
        call_timeout_minutes=loaded.call_timeout_minutes,
        bots=bots,
        max_bots=MAX_BOTS_PER_COMPANY,
        has_bot_token=bool(bots),
        telegram_bot_username=next((b.username for b in bots if b.username), None),
        phones=[CompanyPhoneOut.model_validate(p) for p in loaded.phones],
        locations=[CompanyLocationOut.model_validate(loc) for loc in loaded.locations],
    )


@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED, dependencies=[OwnerOnly])
async def create_company(payload: CompanyCreate, db: DbSession, user: CurrentUser) -> CompanyOut:
    if user.company_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sizda allaqachon kompaniya bor")
    company = Company(
        name=payload.name.strip(),
        owner_id=user.id,
        call_timeout_minutes=get_settings().call_timeout_minutes,
    )
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
    if payload.call_timeout_minutes is not None:
        company.call_timeout_minutes = payload.call_timeout_minutes
    await db.commit()
    return await _company_out(db, company)


@router.post("/bots", response_model=CompanyBotOut, status_code=status.HTTP_201_CREATED, dependencies=[OwnerOnly])
async def add_bot(payload: CompanyBotCreate, db: DbSession, company: OwnCompany) -> CompanyBotOut:
    """Connect one more Telegram bot (up to MAX_BOTS_PER_COMPANY). Several
    bots register clients for the same events in parallel — that is how a
    company absorbs Telegram's per-bot rate limits on big registration days."""
    token = payload.token.strip()
    count = len(
        (await db.scalars(select(CompanyBot.id).where(CompanyBot.company_id == company.id))).all()
    )
    if count >= MAX_BOTS_PER_COMPANY:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Ko'pi bilan {MAX_BOTS_PER_COMPANY} ta bot ulash mumkin"
        )
    bot = CompanyBot(company_id=company.id, token=token)
    db.add(bot)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu token allaqachon ulangan") from None
    settings = get_settings()
    try:
        if settings.multi_process:
            # API workers never run bots: validate statelessly, the bot
            # service picks the change up via the Redis control channel.
            bot.username = await validate_token(token)
        else:
            bot.username = await bot_manager.add_bot(bot.id, company.id, token)
    except DomainError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from None
    await db.commit()
    await notify_bot_token_changed(company.id)
    return CompanyBotOut.model_validate(bot)


@router.delete("/bots/{bot_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[OwnerOnly])
async def delete_bot(bot_id: int, db: DbSession, company: OwnCompany) -> None:
    bot = await db.get(CompanyBot, bot_id)
    if bot is None or bot.company_id != company.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot topilmadi")
    await db.delete(bot)
    await db.commit()
    if not get_settings().multi_process:
        await bot_manager.remove_bot(bot_id)
    await notify_bot_token_changed(company.id)


def _store_logo(
    directory: Path, filename: str, content: bytes, previous: str | None
) -> None:
    """Blocking disk work, kept off the event loop by the caller."""
    directory.mkdir(parents=True, exist_ok=True)
    if previous:
        (directory / previous).unlink(missing_ok=True)
    (directory / filename).write_bytes(content)


@router.post("/logo", response_model=CompanyOut, dependencies=[OwnerOnly])
async def upload_logo(file: UploadFile, db: DbSession, company: OwnCompany) -> CompanyOut:
    settings = get_settings()
    extension = ALLOWED_LOGO_TYPES.get(file.content_type or "")
    if extension is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Logo PNG, JPEG, WebP yoki SVG formatida bo'lishi kerak"
        )
    # one byte past the cap is enough to reject: reading the whole body first
    # let any authenticated owner pull an arbitrarily large upload into memory
    content = await file.read(settings.max_logo_size + 1)
    if len(content) > settings.max_logo_size:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Logo hajmi 2 MB dan oshmasin")

    filename = f"logo-{company.id}-{secrets.token_hex(4)}{extension}"
    await asyncio.to_thread(
        _store_logo, settings.upload_dir, filename, content, company.logo_path
    )
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
