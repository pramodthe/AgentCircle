from fastapi import APIRouter, HTTPException, status

from app.auth import CurrentUser, create_access_token, hash_password, verify_password
from app.dependencies import AccountsDependency, ProfileMediaDependency
from app.profile_media import public_profile_media
from app.schemas import AuthResponse, LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, accounts: AccountsDependency) -> AuthResponse:
    if accounts.get_user_by_email(payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )
    user = accounts.create_user(
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        handle=payload.handle,
    )
    return AuthResponse(
        access_token=create_access_token(user["_id"]),
        user=accounts.public_user(user),
        onboarding=accounts.onboarding_state(user["_id"]),
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, accounts: AccountsDependency) -> AuthResponse:
    user = accounts.get_user_by_email(payload.email)
    # Same message either way so the endpoint cannot be used to enumerate accounts.
    if user is None or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return AuthResponse(
        access_token=create_access_token(user["_id"]),
        user=accounts.public_user(user),
        onboarding=accounts.onboarding_state(user["_id"]),
    )


@router.get("/me")
def me(
    user: CurrentUser, accounts: AccountsDependency, profile_media: ProfileMediaDependency
) -> dict:
    user_id = user["_id"]
    return {
        "user": accounts.public_user(user),
        "profile": {
            **(accounts.get_profile(user_id) or {}),
            **public_profile_media(profile_media.for_users([user_id]).get(user_id)),
        },
        "persona": accounts.get_persona(user_id),
        "onboarding": accounts.onboarding_state(user_id),
    }
