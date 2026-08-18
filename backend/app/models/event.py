import secrets
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, now_utc
from app.models.enums import EventPhase


def _display_code() -> str:
    return secrets.token_urlsafe(8)


class SaleEvent(Base):
    """A sale day. Clients register via the bot beforehand; on the day they
    check in with their QR until ``checkin_until``, after which the queue
    starts, ordered by bot registration time among checked-in tickets."""

    __tablename__ = "sale_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    # optional: which branch (filial) hosts this sale day; the single company
    # bot serves every branch, so this only labels where the sale happens
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime)
    checkin_until: Mapped[datetime] = mapped_column(UTCDateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # public, unguessable code for the TV display page
    display_code: Mapped[str] = mapped_column(
        String(24), unique=True, index=True, default=_display_code
    )
    # monotonically increasing counter for the "end of day" (late) queue group
    late_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)

    company: Mapped["Company"] = relationship(back_populates="events")  # noqa: F821
    branch: Mapped["Branch | None"] = relationship()  # noqa: F821
    tickets: Mapped[list["Ticket"]] = relationship(  # noqa: F821
        back_populates="event", cascade="all, delete-orphan"
    )

    def phase(self, at: datetime | None = None) -> EventPhase:
        at = at or now_utc()
        if not self.is_active:
            return EventPhase.CLOSED
        if at < self.starts_at:
            return EventPhase.REGISTRATION
        if at < self.checkin_until:
            return EventPhase.CHECKIN
        return EventPhase.QUEUE

    def registration_open(self, at: datetime | None = None) -> bool:
        """Bot hands out numbers while the event is active and the scanning
        window has not closed yet."""
        at = at or now_utc()
        return self.is_active and at < self.checkin_until

    def queue_started(self, at: datetime | None = None) -> bool:
        at = at or now_utc()
        return self.is_active and at >= self.checkin_until
