import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import EventPhase, TicketSource, TicketStatus

# the queue "number" is a random 4-letter uppercase code (see ticket_service)
NUMBER_RE = re.compile(r"^[A-Z]{4}$")


def normalize_ticket_number(value: str) -> str:
    number = value.strip().upper()
    if not NUMBER_RE.fullmatch(number):
        raise ValueError("Navbat kodi 4 ta lotin harfidan iborat bo'ladi")
    return number


class EventBranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class EventCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    starts_at: datetime
    checkin_until: datetime
    # one event can run in several branches at once (multiselect)
    branch_ids: list[int] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _check_window(self) -> "EventCreate":
        if self.starts_at.tzinfo is None or self.checkin_until.tzinfo is None:
            raise ValueError("Vaqtlar vaqt mintaqasi bilan yuborilishi kerak (ISO 8601)")
        if self.checkin_until <= self.starts_at:
            raise ValueError("Skanerlash tugash vaqti boshlanish vaqtidan keyin bo'lishi kerak")
        return self


class EventUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    starts_at: datetime | None = None
    checkin_until: datetime | None = None
    is_active: bool | None = None
    # None = unchanged; a list replaces the branch set
    branch_ids: list[int] | None = Field(default=None, max_length=50)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    starts_at: datetime
    checkin_until: datetime
    is_active: bool
    display_code: str
    phase: EventPhase
    branches: list[EventBranchOut] = []
    ticket_count: int = 0
    checked_in_count: int = 0
    branch_id: int | None = None
    branch_name: str | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    code: str
    first_name: str
    last_name: str
    phone: str
    status: TicketStatus
    late: bool
    source: TicketSource
    branch_id: int | None = None
    branch_name: str | None = None
    registered_at: datetime
    checked_in_at: datetime | None
    called_at: datetime | None
    desk_number: int | None = None
    position: int | None = None
    call_count: int
    skip_count: int


class CheckinRequest(BaseModel):
    code: str | None = Field(default=None, max_length=64)
    number: str | None = Field(default=None, max_length=16)

    @field_validator("number")
    @classmethod
    def _normalize_number(cls, v: str | None) -> str | None:
        return None if v is None else normalize_ticket_number(v)

    @model_validator(mode="after")
    def _one_of(self) -> "CheckinRequest":
        if not self.code and self.number is None:
            raise ValueError("QR kod yoki navbat kodi kerak")
        return self


class CallNextRequest(BaseModel):
    desk_id: int


class TicketActionRequest(BaseModel):
    number: str = Field(max_length=16)

    @field_validator("number")
    @classmethod
    def _normalize_number(cls, v: str) -> str:
        return normalize_ticket_number(v)


class SeedRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=100)
