import hashlib
from datetime import timedelta
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from api.auth.dependencies import get_current_user_id
from api.auth.service import create_access_token, hash_password, verify_password
from api.database import get_db_session
from api.models import LoginAttempt, User, utcnow
from api.users.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
_dummy_hash = hash_password("dummy-password-for-timing")


def throttle(db, request, email):
    # IP global y cuenta global: evita eludir el límite cambiando solo uno.
    keys = [hashlib.sha256(value.encode()).hexdigest() for value in ("ip:" + (request.client.host if request.client else "unknown"), "email:" + email)]
    cutoff = utcnow() - timedelta(minutes=1)
    for key in sorted(keys):
        if db.bind.dialect.name == "postgresql":
            db.scalar(select(func.pg_advisory_xact_lock(int(key[:15], 16))))
        count = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key == key, LoginAttempt.created_at >= cutoff))
        if count >= settings.auth.login_attempts:
            raise HTTPException(429, "Demasiados intentos. Intenta nuevamente en un minuto.", headers={"Retry-After": "60"})
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < utcnow() - timedelta(days=1)))
    db.add_all([LoginAttempt(key=key) for key in keys])
    db.commit()


@router.post("/register", response_model=UserResponse, status_code=201)
def register(data: RegisterRequest, request: Request, db=Depends(get_db_session)):
    email = data.email.lower().strip()
    throttle(db, request, email)
    user = User(email=email, password_hash=hash_password(data.password), name=data.name.strip())
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Email already registered") from error
    return UserResponse(id=str(user.id), email=user.email, name=user.name, is_active=user.is_active)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db=Depends(get_db_session)):
    email = data.email.lower().strip()
    throttle(db, request, email)
    user = db.scalar(select(User).where(User.email == email))
    valid = verify_password(data.password, user.password_hash if user else _dummy_hash)
    if not user or not valid:
        raise HTTPException(401, "Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(403, "User is inactive")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
def get_me(current_user_id: Annotated[UUID, Depends(get_current_user_id)], db=Depends(get_db_session)):
    user = db.get(User, current_user_id)
    return UserResponse(id=str(user.id), email=user.email, name=user.name, is_active=user.is_active)
