"""
AI Fitness Coach — Auth API Routes

Handles user registration, login, token refresh, and legacy account migration.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User, generate_uuid
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    TokenRefreshRequest,
    SetPasswordRequest,
    UserResponse,
)
from app.services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.api.deps import get_current_user
from jose import JWTError

router = APIRouter(prefix="/auth", tags=["Auth"])


def _make_token_response(user: User) -> TokenResponse:
    """Helper to create a consistent token response."""
    return TokenResponse(
        access_token=create_access_token(user.id, user.username),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
        username=user.username,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user account. Returns access + refresh tokens."""
    # Check username uniqueness
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    # Check email uniqueness if provided
    if data.email:
        result = await db.execute(select(User).where(User.email == data.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=generate_uuid(),
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return _make_token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate with username + password. Returns access + refresh tokens."""
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")

    return _make_token_response(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    data: TokenRefreshRequest, db: AsyncSession = Depends(get_db)
):
    """Exchange a refresh token for new access + refresh tokens."""
    try:
        payload = decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    return _make_token_response(user)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the currently authenticated user's info."""
    return current_user


@router.post("/set-password", response_model=TokenResponse)
async def set_password(data: SetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Set a password for a legacy user who has no password yet.

    This is a one-time migration endpoint for users created before auth was added.
    Only works if the user's password_hash is NULL.
    """
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.password_hash:
        raise HTTPException(
            status_code=409, detail="Password already set. Use login instead."
        )

    user.password_hash = hash_password(data.password)
    await db.commit()

    return _make_token_response(user)
