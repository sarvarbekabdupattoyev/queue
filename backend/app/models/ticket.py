from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, now_utc
from app.models.enums import TicketSource, TicketStatus

# Tickets checked in late (or returning after a skip) go to the end-of-day
# group. Their queue_order is LATE_ORDER_BASE + a per-event sequence, which is
# far above any epoch-microseconds value used for the on-time group.
LATE_ORDER_BASE = 9_000_000_000_000_000


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("event_id", "number", name="uq_ticket_event_number"),
        UniqueConstraint("event_id", "phone", name="uq_ticket_event_phone"),
        # Hot paths: the waiting list is always read as
        # "event (+ branch) + status CHECKED_IN, ordered by queue_order, id" —
        # calling the next client and every state rebuild run it. Carrying the
        # sort columns in the index turns both into a top-1 index read instead
        # of sorting the whole checked-in set of the event.
        Index("ix_ticket_waiting", "event_id", "status", "queue_order", "id"),
        Index(
            "ix_ticket_waiting_branch",
            "event_id",
            "branch_id",
            "status",
            "queue_order",
            "id",
        ),
        Index("ix_ticket_event_chat", "event_id", "telegram_chat_id"),
        # A desk serves ONE client at a time. The busy check in call_next and
        # the claim that follows it are separate transactions, so this partial
        # unique index is what actually stops two concurrent calls at the same
        # desk from sending two clients to it.
        Index(
            "uq_ticket_desk_active",
            "desk_id",
            unique=True,
            sqlite_where=text("desk_id IS NOT NULL AND status IN ('CALLED', 'SERVING')"),
            postgresql_where=text(
                "desk_id IS NOT NULL AND status IN ('CALLED', 'SERVING')"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("sale_events.id", ondelete="CASCADE"), index=True
    )
    # branch the client registered for (required when the event has branches);
    # queue order, calling and positions are scoped inside one branch
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"), nullable=True
    )
    # bot the client registered through — notifications go out via this bot
    # (a Telegram bot can only message users who started it)
    bot_id: Mapped[int | None] = mapped_column(
        ForeignKey("company_bots.id", ondelete="SET NULL"), nullable=True
    )
    # random (non-sequential) 4-letter uppercase code, unique within the event
    number: Mapped[str] = mapped_column(String(4))
    # opaque code embedded in the QR image, globally unique
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    first_name: Mapped[str] = mapped_column(String(64))
    last_name: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(16))
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    source: Mapped[TicketSource] = mapped_column(
        Enum(TicketSource, native_enum=False, length=8), default=TicketSource.BOT
    )

    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, native_enum=False, length=16),
        default=TicketStatus.REGISTERED,
        index=True,
    )
    # Position key while waiting: epoch microseconds of registered_at for the
    # on-time group; LATE_ORDER_BASE + seq for the end-of-day group.
    queue_order: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    late: Mapped[bool] = mapped_column(Boolean, default=False)

    # sale outcome, answered by the manager when finishing the client:
    # True = a contract was signed, False = no contract, NULL = not recorded
    # (ticket not finished yet, or finished before this question existed)
    contract_signed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    registered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    checked_in_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    called_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    desk_id: Mapped[int | None] = mapped_column(
        ForeignKey("desks.id", ondelete="SET NULL"), nullable=True
    )
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    skip_count: Mapped[int] = mapped_column(Integer, default=0)

    event: Mapped["SaleEvent"] = relationship(back_populates="tickets")  # noqa: F821
    desk: Mapped["Desk | None"] = relationship()  # noqa: F821

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
