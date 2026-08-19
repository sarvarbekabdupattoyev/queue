from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole
from app.schemas.auth import PhoneMixin, UserOut


class EmployeeCreate(PhoneMixin):
    first_name: str = Field(min_length=2, max_length=64)
    last_name: str = Field(default="", max_length=64)
    role: UserRole
    branch_id: int | None = None

    def validated_role(self) -> UserRole:
        return self.role


class EmployeeUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=2, max_length=64)
    last_name: str | None = Field(default=None, max_length=64)
    role: UserRole | None = None
    is_active: bool | None = None
    branch_id: int | None = None
    clear_branch: bool = False


class EmployeeWithPassword(BaseModel):
    employee: UserOut
    password: str


class DeskCreate(BaseModel):
    number: int = Field(ge=1, le=999)
    name: str = Field(default="", max_length=120)
    manager_id: int | None = None
    branch_id: int | None = None


class DeskUpdate(BaseModel):
    number: int | None = Field(default=None, ge=1, le=999)
    name: str | None = Field(default=None, max_length=120)
    manager_id: int | None = None
    clear_manager: bool = False
    branch_id: int | None = None
    clear_branch: bool = False


class DeskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    name: str
    manager_id: int | None
    manager_name: str | None = None
    branch_id: int | None = None
    branch_name: str | None = None
