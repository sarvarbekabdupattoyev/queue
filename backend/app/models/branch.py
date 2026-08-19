from datetime import datetime

from sqlalchemy import Column, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, now_utc

# One sale event can run in several branches at once; managers and desks are
# branch-specific, so each branch serves its own slice of the event's queue.
event_branches = Table(
    "event_branches",
    Base.metadata,
    Column(
        "event_id",
        ForeignKey("sale_events.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "branch_id",
        ForeignKey("branches.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Branch(Base):
    """A company office/branch ("filial"). Optional: companies with a single
    office keep everything unscoped (branch_id NULL everywhere)."""

    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_branch_company_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)

    company: Mapped["Company"] = relationship(back_populates="branches")  # noqa: F821
