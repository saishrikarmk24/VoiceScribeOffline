"""Authentication, RBAC and data-protection abstractions.

The prototype ships a *development* identity provider: the client may declare an
identity through ``X-User-Email`` / ``X-User-Role`` headers, otherwise the
configured development user is used. The dependency surface
(``get_current_principal``, ``require_roles``) is the same one a real OIDC/JWT
provider would satisfy, so swapping it does not touch the routes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Annotated, Iterable

from fastapi import Depends, Header, HTTPException, status

from app.core.config import settings
from app.models.enums import UserRole


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a cryptographically secure random salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}${key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a stored PBKDF2-HMAC-SHA256 hash."""
    try:
        salt_hex, key_hex = hashed.split("$")
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(key, expected_key)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta_seconds: int = 86400 * 7) -> str:
    """Create an HMAC-SHA256 signed access token."""
    payload = dict(data)
    payload["exp"] = int(time.time()) + expires_delta_seconds
    raw_payload = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw_payload).decode("utf-8").rstrip("=")
    sig = hmac.new(settings.secret_key.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{sig}"


def decode_access_token(token: str) -> dict | None:
    """Verify signature and return the token payload, or None if invalid/expired."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        b64_payload, signature = parts
        expected_sig = hmac.new(
            settings.secret_key.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Pad base64 urlsafe string
        padding = "=" * ((4 - len(b64_payload) % 4) % 4)
        raw_json = base64.urlsafe_b64decode(b64_payload + padding).decode("utf-8")
        payload = json.loads(raw_json)

        exp = payload.get("exp")
        if exp is not None and time.time() > float(exp):
            return None  # expired
        return payload
    except Exception:
        return None


@dataclass(slots=True)
class Principal:
    email: str
    role: UserRole
    display_name: str
    doctor_id: str | None = None
    user_id: str | None = None
    department: str | None = None
    development: bool = True

    @property
    def is_admin(self) -> bool:
        return self.role is UserRole.ADMIN

    def can_approve_notes(self) -> bool:
        return self.role in (UserRole.DOCTOR, UserRole.FACULTY, UserRole.ADMIN)

    def can_manage_sessions(self) -> bool:
        return self.role in (UserRole.DOCTOR, UserRole.FACULTY, UserRole.ADMIN, UserRole.STUDENT)


def _parse_role(raw: str | None) -> UserRole:
    if not raw:
        return UserRole(settings.dev_user_role)
    try:
        return UserRole(raw.strip().upper())
    except ValueError:
        return UserRole(settings.dev_user_role)


async def get_current_principal(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_user_email: Annotated[str | None, Header(alias="X-User-Email")] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> Principal:
    # 1. Try Bearer token from Authorization header
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        payload = decode_access_token(token)
        if payload:
            email = str(payload.get("email", "")).strip().lower()
            role = _parse_role(payload.get("role"))
            display = payload.get("full_name") or email.split("@")[0].replace(".", " ").title()
            doctor_id = payload.get("doctor_id")
            user_id = payload.get("user_id")
            department = payload.get("department")
            return Principal(
                email=email,
                role=role,
                display_name=display,
                doctor_id=doctor_id,
                user_id=user_id,
                department=department,
                development=False,
            )

    # 2. Try development header fallback
    if settings.dev_auth_enabled:
        email = (x_user_email or settings.dev_user_email).strip().lower()
        role = _parse_role(x_user_role)
        display = email.split("@")[0].replace(".", " ").title()
        return Principal(email=email, role=role, display_name=display, development=True)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication credentials.",
    )


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_roles(*roles: UserRole):
    """Dependency factory enforcing role-based access control."""

    allowed: set[UserRole] = set(roles) or set(UserRole)

    async def _dependency(principal: CurrentPrincipal) -> Principal:
        if principal.role not in allowed and principal.role is not UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {principal.role.value} is not permitted to perform this action.",
            )
        return principal

    return _dependency


class EncryptedStorage:
    """Abstraction for encryption at rest.

    The prototype stores audio and transcripts unencrypted on the local
    filesystem/database. This class marks the boundary where a KMS-backed
    envelope encryption implementation belongs, and provides a keyed digest used
    for tamper-evident audit entries.
    """

    enabled = False

    def __init__(self, secret_key: str | None = None) -> None:
        self.secret_key = (secret_key or settings.secret_key).encode("utf-8")

    def fingerprint(self, payload: bytes) -> str:
        return hmac.new(self.secret_key, payload, hashlib.sha256).hexdigest()

    def encrypt(self, payload: bytes) -> bytes:
        if not self.enabled:  # pragma: no cover - documented no-op
            return payload
        raise NotImplementedError("Wire a KMS/HSM backend before enabling encrypted storage.")

    def decrypt(self, payload: bytes) -> bytes:
        if not self.enabled:  # pragma: no cover - documented no-op
            return payload
        raise NotImplementedError("Wire a KMS/HSM backend before enabling encrypted storage.")

    def describe(self) -> dict[str, object]:
        return {
            "encryption_at_rest": self.enabled,
            "retention_days": settings.data_retention_days,
            "note": "Enable a KMS backend before any real clinical use.",
        }


storage_protection = EncryptedStorage()


def roles_allowing(*roles: UserRole) -> Iterable[str]:
    return [role.value for role in roles]
