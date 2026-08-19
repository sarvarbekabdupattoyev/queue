from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, now_utc
from app.models.enums import UserRole


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # A phone is unique inside one company only: two different companies
        # may each employ (or be owned by) the same phone number.
        UniqueConstraint("company_id", "phone", name="uq_user_company_phone"),
        # Owners sign up before they have a company (company_id is NULL, which
        # the composite constraint cannot police), so owner accounts get their
        # own phone uniqueness via a partial index.
        Index(
            "uq_users_owner_phone",
            "phone",
            unique=True,
            sqlite_where=text("role = 'OWNER'"),
            postgresql_where=text("role = 'OWNER'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(16), index=True)
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
