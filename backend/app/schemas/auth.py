from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.phone import normalize_phone
from app.models.enums import UserRole


class PhoneMixin(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def _normalize(cls, v: str) -> str:
        normalized = normalize_phone(v)
        if not normalized:
            raise ValueError("Telefon raqami noto'g'ri. Format: +998 XX XXX XX XX")
        return normalized


class RegisterRequest(PhoneMixin):
    first_name: str = Field(min_length=2, max_length=64)
    last_name: str = Field(default="", max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(PhoneMixin):
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    first_name: str
    last_name: str
    role: UserRole
    company_id: int | None
    branch_id: int | None = None
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
