import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_token,
    refresh_token_expiry,
    set_auth_cookies,
    verify_password,
)
from app.db.models.session import Session
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name or user.email,
        created_at=user.created_at,
    )


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    await db.flush()

    raw_token, token_hash = create_refresh_token()
    session = Session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=refresh_token_expiry(),
    )
    db.add(session)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(str(user.id))
    set_auth_cookies(response, access_token, raw_token)

    logger.info("User registered: %s", user.id)
    return _user_response(user)


@router.post("/login", response_model=UserResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    raw_token, token_hash = create_refresh_token()
    session = Session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=refresh_token_expiry(),
    )
    db.add(session)
    await db.commit()

    access_token = create_access_token(str(user.id))
    set_auth_cookies(response, access_token, raw_token)

    logger.info("User logged in: %s", user.id)
    return _user_response(user)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    raw_token = request.cookies.get("refresh_token")
    if raw_token:
        token_hash = hash_token(raw_token)
        result = await db.execute(
            select(Session).where(Session.token_hash == token_hash)
        )
        session = result.scalar_one_or_none()
        if session:
            await db.delete(session)
            await db.commit()

    clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _user_response(current_user)


@router.post("/refresh", response_model=UserResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    raw_token = request.cookies.get("refresh_token")
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    token_hash = hash_token(raw_token)
    result = await db.execute(select(Session).where(Session.token_hash == token_hash))
    session = result.scalar_one_or_none()

    expires = session.expires_at if session and session.expires_at.tzinfo else (
        session.expires_at.replace(tzinfo=timezone.utc) if session else None
    )
    if not session or expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = await db.get(User, session.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Rotate: delete old session, create new one
    await db.delete(session)
    raw_new, hash_new = create_refresh_token()
    new_session = Session(
        user_id=user.id,
        token_hash=hash_new,
        expires_at=refresh_token_expiry(),
    )
    db.add(new_session)
    await db.commit()

    access_token = create_access_token(str(user.id))
    set_auth_cookies(response, access_token, raw_new)

    return _user_response(user)
