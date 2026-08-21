from pydantic import BaseModel, ConfigDict, Field

from app.models.company import MAX_BOTS_PER_COMPANY
from app.schemas.auth import PhoneMixin


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    call_timeout_minutes: int | None = Field(default=None, ge=1, le=60)


class CompanyBotCreate(BaseModel):
    token: str = Field(min_length=10, max_length=64)


class CompanyBotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str | None


class CompanyPhoneCreate(PhoneMixin):
    label: str = Field(default="", max_length=64)


class CompanyPhoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    label: str


class CompanyLocationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    address: str = Field(default="", max_length=255)
    map_url: str = Field(default="", max_length=255)


class CompanyLocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str
    map_url: str


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    logo_url: str | None = None
    call_timeout_minutes: int
    # up to MAX_BOTS_PER_COMPANY parallel bots (tokens never leave the server)
    bots: list[CompanyBotOut] = []
    max_bots: int = MAX_BOTS_PER_COMPANY
    has_bot_token: bool = False
    telegram_bot_username: str | None = None
    phones: list[CompanyPhoneOut] = []
    locations: list[CompanyLocationOut] = []
