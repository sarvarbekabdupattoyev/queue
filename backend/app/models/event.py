import secrets
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, now_utc
from app.models.branch import Branch, event_branches
from app.models.enums import EventPhase


def _display_code() -> str:
    return secrets.token_urlsafe(8)


class SaleEvent(Base):
    """A sale day, run in three clearly separated periods:

    1. registration (… → ``registration_until``): the bot registers clients
       and hands out QR + code. Registration never actually closes until the
       sale ends — clients who register later simply join the late group.
    2. QR scanning (``starts_at`` → ``checkin_until``): reception scans QR
       codes. Scans after ``checkin_until`` are still accepted but go to the
       late (end-of-day) group.
    3. sale (``sale_starts_at`` → until the queue drains or the owner ends
       it): calling is open. The owner can put the sale ON HOLD (calling
       pauses, scanning continues) and resume it where it stopped.
    """

    __tablename__ = "sale_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    # end of the ON-TIME registration period: clients registered after this
    # moment get a QR too, but land in the late group once scanned
    registration_until: Mapped[datetime] = mapped_column(UTCDateTime)
    # QR scanning period (start is informational; the end is the on-time cut)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime)
    checkin_until: Mapped[datetime] = mapped_column(UTCDateTime)
    # the sale (calling) starts here; it has no fixed end
    sale_starts_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # owner controls over the running sale
    sale_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    sale_ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # set once the sale-start Telegram burst went out (atomic claim)
    sale_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # public, unguessable code for the TV display page
    display_code: Mapped[str] = mapped_column(
        String(24), unique=True, index=True, default=_display_code
    )
    # monotonically increasing counter for the "end of day" (late) queue group
    late_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)

    company: Mapped["Company"] = relationship(back_populates="events")  # noqa: F821
    # branches the event runs in; empty = single-office event (no scoping).
    # Replaces the earlier single `branch_id` column — one sale day can run in
    # several branches at once, each with its own desks and queue.
    # lazy="selectin" keeps the list available in async code paths without
    # explicit eager-load options at every call site.
    branches: Mapped[list[Branch]] = relationship(
        secondary=event_branches, order_by=Branch.id, lazy="selectin"
    )
    tickets: Mapped[list["Ticket"]] = relationship(  # noqa: F821
        back_populates="event", cascade="all, delete-orphan"
    )

    def branch_ids(self) -> list[int]:
        return [b.id for b in self.branches]

    def phase(self, at: datetime | None = None) -> EventPhase:
        at = at or now_utc()
        if not self.is_active:
            return EventPhase.CLOSED
        if self.sale_ended_at is not None:
            return EventPhase.ENDED
        if at < self.registration_until:
            return EventPhase.REGISTRATION
        if at < self.sale_starts_at:
            return EventPhase.CHECKIN
        if self.sale_hold:
            return EventPhase.HOLD
        return EventPhase.QUEUE

    def registration_open(self, at: datetime | None = None) -> bool:
        """The bot hands out codes for as long as the event is active and the
        sale has not ended — late registrants just join the late group."""
        return self.is_active and self.sale_ended_at is None

    def queue_started(self, at: datetime | None = None) -> bool:
        """The sale (calling period) has begun and is not over. A sale on
        hold still counts as started — only calling is paused."""
        at = at or now_utc()
        return self.is_active and self.sale_ended_at is None and at >= self.sale_starts_at

    def on_time_checkin(self, ticket_registered_at: datetime, at: datetime | None = None) -> bool:
        """A scan joins the main queue only when the client registered inside
        the registration period AND the scan lands inside the QR window;
        everything else goes to the late (end-of-day) group."""
        at = at or now_utc()
        return ticket_registered_at <= self.registration_until and at < self.checkin_until
