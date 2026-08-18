from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Company, SaleEvent, User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Avtorizatsiya talab qilinadi")
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token yaroqsiz yoki muddati o'tgan")
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Foydalanuvchi topilmadi yoki bloklangan")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
        return user

    return checker


OwnerUser = Annotated[User, Depends(require_roles(UserRole.OWNER))]
StaffUser = Annotated[
    User, Depends(require_roles(UserRole.OWNER, UserRole.MANAGER, UserRole.SCANNER))
]
ManagerUser = Annotated[User, Depends(require_roles(UserRole.OWNER, UserRole.MANAGER))]


async def get_own_company(db: DbSession, user: CurrentUser) -> Company:
    if user.company_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kompaniya hali yaratilmagan")
    company = await db.get(Company, user.company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kompaniya topilmadi")
    return company


OwnCompany = Annotated[Company, Depends(get_own_company)]


async def get_company_event(event_id: int, db: DbSession, user: CurrentUser) -> SaleEvent:
    event = await db.get(SaleEvent, event_id)
    if event is None or event.company_id != user.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tadbir topilmadi")
    return event


CompanyEvent = Annotated[SaleEvent, Depends(get_company_event)]
