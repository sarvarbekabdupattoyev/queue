from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.security import (
    create_access_token,
    hash_password_async,
    verify_password_async,
)
from app.models import User, UserRole
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: DbSession) -> TokenResponse:
    """Sign up a client (company owner). Employees are created by their owner.

    Owner phones are unique among owners only: the same phone may already be
    an employee of some other company — that must not block a new sign-up.
    """
    existing = await db.scalar(
        select(User.id).where(User.phone == payload.phone, User.role == UserRole.OWNER)
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu raqam allaqachon ro'yxatdan o'tgan")
    user = User(
        phone=payload.phone,
        password_hash=await hash_password_async(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        role=UserRole.OWNER,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # lost a race with a concurrent sign-up of the same phone
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Bu raqam allaqachon ro'yxatdan o'tgan"
        ) from None
    await db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    # One phone may hold accounts in several companies (e.g. a manager hired
    # by two clients) — the password picks the account. Active accounts are
    # tried first so a deactivated duplicate cannot shadow a working one.
    candidates = (
        await db.scalars(
            select(User)
            .where(User.phone == payload.phone)
            .order_by(User.is_active.desc(), User.id)
        )
    ).all()
    user = None
    for candidate in candidates:
        if await verify_password_async(payload.password, candidate.password_hash):
            user = candidate
            break
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Telefon raqam yoki parol noto'g'ri")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hisobingiz bloklangan — rahbaringizga murojaat qiling")
    return TokenResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
