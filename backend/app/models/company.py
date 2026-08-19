from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, now_utc

# Telegram caps a single bot at ~30 messages/second, so companies expecting a
# registration rush (up to ~10 000 sign-ups a minute on sale days) may connect
# several bots that serve the same queue in parallel.
MAX_BOTS_PER_COMPANY = 3


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    # use_alter breaks the users↔companies FK cycle for CREATE/DROP ordering
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", use_alter=True, name="fk_company_owner")
    )
    logo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)

    owner: Mapped["User"] = relationship(foreign_keys=[owner_id])  # noqa: F821
    members: Mapped[list["User"]] = relationship(  # noqa: F821
        back_populates="company", foreign_keys="User.company_id"
    )
    phones: Mapped[list["CompanyPhone"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="CompanyPhone.id"
    )
    locations: Mapped[list["CompanyLocation"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="CompanyLocation.id"
    )
    branches: Mapped[list["Branch"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan", order_by="Branch.id"
    )
    bots: Mapped[list["CompanyBot"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="CompanyBot.id",
        lazy="selectin",
    )
    desks: Mapped[list["Desk"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan", order_by="Desk.number"
    )
    events: Mapped[list["SaleEvent"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )


class CompanyBot(Base):
    """One Telegram bot of a company (up to MAX_BOTS_PER_COMPANY). All bots of
    a company run the same registration flow in parallel — this spreads
    Telegram's per-bot rate limits during registration bursts. Each ticket
    remembers the bot it came from so notifications go out through a bot the
    client has actually started."""

    __tablename__ = "company_bots"
    __table_args__ = (UniqueConstraint("token", name="uq_company_bot_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(64))
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)

    company: Mapped[Company] = relationship(back_populates="bots")


class CompanyPhone(Base):
    __tablename__ = "company_phones"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    phone: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(64), default="")

    company: Mapped[Company] = relationship(back_populates="phones")


class CompanyLocation(Base):
    __tablename__ = "company_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255), default="")
    map_url: Mapped[str] = mapped_column(String(255), default="")

    company: Mapped[Company] = relationship(back_populates="locations")
