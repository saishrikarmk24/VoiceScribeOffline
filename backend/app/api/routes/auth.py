"""Authentication and Doctor ID provisioning routes."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentPrincipal, DbSession
from app.core.security import (
    create_access_token,
    hash_password,
    require_roles,
    verify_password,
)
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import (
    AdminRegisterRequest,
    AuthResponse,
    DoctorCreateRequest,
    DoctorPasswordReset,
    DoctorStatusUpdate,
    LoginRequest,
    UserOut,
)
from app.schemas.common import Acknowledgement

router = APIRouter(prefix="/auth", tags=["auth"])


def _serialize_user(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        doctor_id=user.doctor_id,
        department=user.department,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, db: DbSession) -> AuthResponse:
    """Authenticate a doctor (via Doctor ID or Email) or an administrator."""
    identifier = payload.identifier.strip()
    if not identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor ID or Email is required."
        )

    # Lookup by Doctor ID (case-insensitive) or Email
    query = select(User).where(
        (func.lower(User.doctor_id) == identifier.lower()) | (func.lower(User.email) == identifier.lower())
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Doctor ID/Email or password. Please verify your credentials.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Please contact the administrator.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    token = create_access_token(
        {
            "user_id": str(user.id),
            "email": user.email,
            "role": user.role.value,
            "full_name": user.full_name,
            "doctor_id": user.doctor_id,
            "department": user.department,
        }
    )

    return AuthResponse(token=token, user=_serialize_user(user))


@router.post("/admin/register", response_model=AuthResponse)
async def admin_register(payload: AdminRegisterRequest, db: DbSession) -> AuthResponse:
    """Register an administrator. If an admin already exists, public signup is locked."""
    existing_admin_count = (
        await db.execute(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN))
    ).scalar() or 0

    if existing_admin_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An administrator already exists. Please log in with existing admin credentials.",
        )

    existing_email = (
        await db.execute(select(User).where(func.lower(User.email) == payload.email.lower()))
    ).scalar_one_or_none()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists."
        )

    admin_user = User(
        email=payload.email.lower().strip(),
        full_name=payload.full_name.strip(),
        doctor_id="ADMIN",
        department="Hospital Administration",
        password_hash=hash_password(payload.password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin_user)
    await db.commit()
    await db.refresh(admin_user)

    token = create_access_token(
        {
            "user_id": str(admin_user.id),
            "email": admin_user.email,
            "role": admin_user.role.value,
            "full_name": admin_user.full_name,
            "doctor_id": admin_user.doctor_id,
            "department": admin_user.department,
        }
    )

    return AuthResponse(token=token, user=_serialize_user(admin_user))


@router.get("/me", response_model=UserOut)
async def get_me(principal: CurrentPrincipal, db: DbSession) -> UserOut:
    """Return profile of currently logged-in user."""
    user = (
        await db.execute(select(User).where(func.lower(User.email) == principal.email.lower()))
    ).scalar_one_or_none()
    if user is not None:
        return _serialize_user(user)

    # Return principal as virtual user if in dev mock mode
    return UserOut(
        id=principal.user_id or str(uuid.uuid4()),
        email=principal.email,
        full_name=principal.display_name,
        doctor_id=principal.doctor_id or "DEV-DOC",
        department=principal.department or "General Medicine",
        role=principal.role,
        is_active=True,
    )


@router.get("/doctors", response_model=list[UserOut])
async def list_doctors(
    principal: Annotated[CurrentPrincipal, Depends(require_roles(UserRole.ADMIN))],
    db: DbSession,
) -> list[UserOut]:
    """Admin-only: list all provisioned doctors."""
    query = select(User).where(User.role == UserRole.DOCTOR).order_by(User.created_at.desc())
    result = await db.execute(query)
    doctors = result.scalars().all()
    return [_serialize_user(doc) for doc in doctors]


@router.post("/doctors", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def provision_doctor(
    payload: DoctorCreateRequest,
    principal: Annotated[CurrentPrincipal, Depends(require_roles(UserRole.ADMIN))],
    db: DbSession,
) -> UserOut:
    """Admin-only: provision a new doctor with a unique Doctor ID and initial credentials."""
    doctor_id = payload.doctor_id.strip().upper()
    email = payload.email.strip().lower()

    # Check for doctor_id uniqueness
    existing_id = (
        await db.execute(select(User).where(func.upper(User.doctor_id) == doctor_id))
    ).scalar_one_or_none()
    if existing_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Doctor ID '{doctor_id}' is already assigned to another doctor.",
        )

    # Check for email uniqueness
    existing_email = (
        await db.execute(select(User).where(func.lower(User.email) == email))
    ).scalar_one_or_none()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{email}' is already registered.",
        )

    doctor = User(
        doctor_id=doctor_id,
        email=email,
        full_name=payload.full_name.strip(),
        department=payload.department.strip(),
        password_hash=hash_password(payload.password),
        role=UserRole.DOCTOR,
        is_active=True,
        created_by=principal.email,
    )
    db.add(doctor)
    await db.commit()
    await db.refresh(doctor)
    return _serialize_user(doctor)


@router.patch("/doctors/{doctor_uuid}/status", response_model=UserOut)
async def update_doctor_status(
    doctor_uuid: str,
    payload: DoctorStatusUpdate,
    principal: Annotated[CurrentPrincipal, Depends(require_roles(UserRole.ADMIN))],
    db: DbSession,
) -> UserOut:
    """Admin-only: toggle active/suspended status for a doctor."""
    doctor = (
        await db.execute(select(User).where(User.id == doctor_uuid))
    ).scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found.")

    doctor.is_active = payload.is_active
    await db.commit()
    await db.refresh(doctor)
    return _serialize_user(doctor)


@router.post("/doctors/{doctor_uuid}/reset_password", response_model=Acknowledgement)
async def reset_doctor_password(
    doctor_uuid: str,
    payload: DoctorPasswordReset,
    principal: Annotated[CurrentPrincipal, Depends(require_roles(UserRole.ADMIN))],
    db: DbSession,
) -> Acknowledgement:
    """Admin-only: reset a doctor's access password."""
    doctor = (
        await db.execute(select(User).where(User.id == doctor_uuid))
    ).scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found.")

    doctor.password_hash = hash_password(payload.new_password)
    await db.commit()
    return Acknowledgement(
        ok=True, message=f"Password for doctor {doctor.doctor_id or doctor.full_name} updated successfully."
    )
