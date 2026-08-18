from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, now_utc


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    # use_alter breaks the users↔companies FK cycle for CREATE/DROP ordering
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", use_alter=True, name="fk_company_owner")
    )
    logo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_bot_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_bot_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
    desks: Mapped[list["Desk"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan", order_by="Desk.number"
    )
    events: Mapped[list["SaleEvent"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )


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
