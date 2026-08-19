from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, now_utc


class BotUser(Base):
    """Per-company bot chat preferences — currently the chosen language.

    One row per (company, chat): all parallel bots of a company share it, so
    the client keeps their language whichever of the company's bots they
    write to, and queue notifications go out in that language."""

    __tablename__ = "bot_users"
    __table_args__ = (UniqueConstraint("company_id", "chat_id", name="uq_bot_user_company_chat"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    language: Mapped[str] = mapped_column(String(8), default="uz")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
