"""Authentication, login, and Doctor provisioning request/response schemas."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    """Identifier can be either Doctor ID (e.g. DOC-101) or Email."""

    identifier: str = Field(description="Doctor ID (e.g. DOC-101) or Email address")
    password: str = Field(min_length=1, description="Account password")


class AdminRegisterRequest(BaseModel):
    """Initial Admin account creation."""

    full_name: str = Field(min_length=2, max_length=128)
    email: str = Field(min_length=3, max_length=256)
    password: str = Field(min_length=6, max_length=128)


class DoctorCreateRequest(BaseModel):
    """Admin-only doctor provisioning."""

    doctor_id: str = Field(
        min_length=2,
        max_length=64,
        description="Assigned unique Doctor ID (e.g. DOC-1001, DR-SMITH)",
    )
    full_name: str = Field(min_length=2, max_length=128)
    email: str = Field(min_length=3, max_length=256)
    department: str = Field(default="General Medicine", max_length=128)
    password: str = Field(min_length=6, max_length=128, description="Initial login password")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    doctor_id: str | None = None
    department: str | None = None
    role: UserRole
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class DoctorStatusUpdate(BaseModel):
    is_active: bool


class DoctorPasswordReset(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)
