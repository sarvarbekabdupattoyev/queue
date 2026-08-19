from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Desk(Base):
    """A manager's table ("stol") that clients are called to. When the company
    has branches every desk belongs to one branch and only serves that
    branch's slice of the queue."""

    __tablename__ = "desks"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "branch_id", "number", name="uq_desk_company_branch_number"
        ),
        # branch_id NULL escapes the composite constraint (NULL != NULL in
        # SQL), so branch-less desks get their own partial unique index
        Index(
            "uq_desk_company_number_nobranch",
            "company_id",
            "number",
            unique=True,
            sqlite_where=text("branch_id IS NULL"),
            postgresql_where=text("branch_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    # desks live inside a branch; deleting the branch removes its desks
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120), default="")
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship(back_populates="desks")  # noqa: F821
    branch: Mapped["Branch | None"] = relationship()  # noqa: F821
    manager: Mapped["User | None"] = relationship(foreign_keys=[manager_id])  # noqa: F821
