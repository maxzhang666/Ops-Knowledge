import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, UUIDMixin


class DepartmentRole(str, enum.Enum):
    DEPT_ADMIN = "dept_admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class Department(Base, UUIDMixin):
    __tablename__ = "departments"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parent_department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    children: Mapped[list["Department"]] = relationship(
        "Department", back_populates="parent", cascade="all, delete-orphan"
    )
    parent: Mapped["Department | None"] = relationship(
        "Department", back_populates="children", remote_side="Department.id"
    )
    members: Mapped[list["UserDepartment"]] = relationship(
        "UserDepartment", back_populates="department", cascade="all, delete-orphan"
    )
    resources: Mapped[list["DepartmentResource"]] = relationship(
        "DepartmentResource", back_populates="department", cascade="all, delete-orphan"
    )


class UserDepartment(Base, UUIDMixin):
    __tablename__ = "user_departments"
    __table_args__ = (UniqueConstraint("user_id", "department_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[DepartmentRole] = mapped_column(
        Enum(DepartmentRole, name="department_role", values_callable=lambda e: [x.value for x in e]),
        nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    department: Mapped["Department"] = relationship("Department", back_populates="members")
    user = relationship("app.auth.models.User", lazy="joined")


class DepartmentResource(Base, UUIDMixin):
    __tablename__ = "department_resources"
    __table_args__ = (UniqueConstraint("department_id", "resource_type", "resource_id"),)

    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    access_level: Mapped[str] = mapped_column(String(20), nullable=False)
    shared_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    department: Mapped["Department"] = relationship("Department", back_populates="resources")
