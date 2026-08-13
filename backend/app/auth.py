"""Password hashing, JWT issuance, and the request-scoped current-user dependency.

The user identity behind a request comes from a signed token and nothing else. Store
methods take an owner ID from this module's dependencies, never from a request body,
so a client cannot act on behalf of another account by naming it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.accounts import AccountStore
from app.settings import Settings, get_settings

# bcrypt truncates silently past 72 bytes; reject instead so a long password is never
# quietly equivalent to its prefix.
MAX_PASSWORD_BYTES = 72

# The value shipped in .env.example. Anyone who has read the repo can forge a token
# signed with it, so it must never reach a deployment.
DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"
MIN_JWT_SECRET_BYTES = 32


def assert_signing_key_is_safe(settings: Settings) -> None:
    """Refuse to start with the public dev secret against a non-local database.

    A warning would be the obvious choice here and the wrong one: a warning that can
    be ignored is not a safeguard, and this is the failure that hands someone else's
    account to anyone who has read the repo. The local-database carve-out keeps
    development frictionless, which is the only reason the default exists.
    """
    secret = settings.jwt_secret.get_secret_value()
    if secret != DEV_JWT_SECRET:
        if len(secret.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
            raise RuntimeError(
                f"JWT_SECRET is only {len(secret.encode('utf-8'))} bytes. Use at least "
                f"{MIN_JWT_SECRET_BYTES}: python -c \"import secrets; "
                'print(secrets.token_urlsafe(48))"'
            )
        return

    local = settings.use_mock_mongodb or any(
        marker in settings.mongodb_uri for marker in ("localhost", "127.0.0.1")
    )
    if not local:
        raise RuntimeError(
            "JWT_SECRET is still the public example value from .env.example, but this "
            "process is pointed at a remote database. Anyone who has read the repo "
            "could forge a session. Generate one with:\n"
            '    python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError("Password must be at most 72 bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings | None = None) -> str | None:
    """Return the subject of a valid token, or None when it is invalid or expired."""
    settings = settings or get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) and subject else None


def _accounts(request: Request) -> AccountStore:
    return request.app.state.accounts


CredentialsDependency = Annotated[
    HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
]


def get_current_user(request: Request, credentials: CredentialsDependency) -> dict:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session expired. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = _accounts(request).get_user(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user_optional(
    request: Request, credentials: CredentialsDependency
) -> dict | None:
    """Resolve a user when a valid token is present, without requiring one."""
    if credentials is None or not credentials.credentials:
        return None
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        return None
    return _accounts(request).get_user(user_id)


CurrentUser = Annotated[dict, Depends(get_current_user)]
OptionalUser = Annotated[dict | None, Depends(get_current_user_optional)]
