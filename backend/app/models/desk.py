from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Desk(Base):
    """A manager's table ("stol") that clients are called to."""

    __tablename__ = "desks"
    __table_args__ = (UniqueConstraint("company_id", "number", name="uq_desk_company_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120), default="")
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship(back_populates="desks")  # noqa: F821
    manager: Mapped["User | None"] = relationship(foreign_keys=[manager_id])  # noqa: F821
