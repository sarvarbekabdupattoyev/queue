from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, now_utc


class Branch(Base):
    """An optional company branch (filial). The company keeps a single
    Telegram bot for every branch; events are pinned to a branch so the bot
    can tell clients where the sale happens."""

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
