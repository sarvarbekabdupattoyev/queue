from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import PhoneMixin


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    # empty string clears the token (stops the bot)
    telegram_bot_token: str | None = None


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
    telegram_bot_username: str | None = None
    has_bot_token: bool = False
    phones: list[CompanyPhoneOut] = []
    locations: list[CompanyLocationOut] = []
