from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, now_utc
from app.models.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    first_name: Mapped[str] = mapped_column(String(64))
    last_name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False, length=16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # branch the employee works at; NULL = whole company (owners, single-office)
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)

    company: Mapped["Company | None"] = relationship(  # noqa: F821
        back_populates="members", foreign_keys=[company_id]
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
