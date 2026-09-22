from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Participant / Staff user with credentials and role."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    doctor_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True, default="")
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=32), default=UserRole.DOCTOR, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
