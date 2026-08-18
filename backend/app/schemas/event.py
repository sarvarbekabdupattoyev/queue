from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EventPhase, TicketSource, TicketStatus


class EventCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    starts_at: datetime
    checkin_until: datetime

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


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    starts_at: datetime
    checkin_until: datetime
    is_active: bool
    display_code: str
    phase: EventPhase
    ticket_count: int = 0
    checked_in_count: int = 0


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    code: str
    first_name: str
    last_name: str
    phone: str
    status: TicketStatus
    late: bool
    source: TicketSource
    registered_at: datetime
    checked_in_at: datetime | None
    called_at: datetime | None
    desk_number: int | None = None
    position: int | None = None
    call_count: int
    skip_count: int


class CheckinRequest(BaseModel):
    code: str | None = None
    number: int | None = None

    @model_validator(mode="after")
    def _one_of(self) -> "CheckinRequest":
        if not self.code and self.number is None:
            raise ValueError("QR kod yoki navbat raqami kerak")
        return self


class CallNextRequest(BaseModel):
    desk_id: int


class TicketActionRequest(BaseModel):
    number: int


class SeedRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=100)
