import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import EventPhase, TicketSource, TicketStatus
from app.schemas.auth import PhoneMixin

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


PERIOD_ORDER_ERROR = (
    "Davrlar tartibi: ro'yxat boshlanishi ≤ skanerlash boshlanishi < skanerlash "
    "tugashi ≤ sotuv boshlanishi"
)


def check_period_order(
    registration_starts_at: datetime,
    starts_at: datetime,
    checkin_until: datetime,
    sale_starts_at: datetime,
) -> bool:
    return registration_starts_at <= starts_at < checkin_until <= sale_starts_at


class EventCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    # the three periods: registration (opens here) → QR scanning → sale
    registration_starts_at: datetime
    starts_at: datetime
    checkin_until: datetime
    sale_starts_at: datetime
    # one event can run in several branches at once (multiselect)
    branch_ids: list[int] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _check_window(self) -> "EventCreate":
        times = (
            self.registration_starts_at,
            self.starts_at,
            self.checkin_until,
            self.sale_starts_at,
        )
        if any(t.tzinfo is None for t in times):
            raise ValueError("Vaqtlar vaqt mintaqasi bilan yuborilishi kerak (ISO 8601)")
        if not check_period_order(*times):
            raise ValueError(PERIOD_ORDER_ERROR)
        return self


class EventUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    registration_starts_at: datetime | None = None
    starts_at: datetime | None = None
    checkin_until: datetime | None = None
    sale_starts_at: datetime | None = None
    is_active: bool | None = None
    # None = unchanged; a list replaces the branch set
    branch_ids: list[int] | None = Field(default=None, max_length=50)


class SaleActionRequest(BaseModel):
    """Owner controls over the running sale."""

    action: Literal["hold", "resume", "end", "reopen"]


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    registration_starts_at: datetime
    starts_at: datetime
    checkin_until: datetime
    sale_starts_at: datetime
    sale_hold: bool
    sale_ended_at: datetime | None
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
    # sale outcome recorded at finish: True = contract signed, False = no
    # contract, None = not recorded
    contract_signed: bool | None = None
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


class DoneRequest(TicketActionRequest):
    """Finishing a client also records the sale outcome the manager picked
    in the "was a contract signed?" dialog (None = not answered)."""

    contract_signed: bool | None = None


class SeedRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=100)


class WalkinCreate(PhoneMixin):
    """A client added at the door by the owner or the QR scanner — goes
    straight to the end of the queue."""

    first_name: str = Field(min_length=2, max_length=64)
    last_name: str = Field(default="", max_length=64)
    branch_id: int | None = None
