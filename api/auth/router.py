from typing import Annotated
from uuid import UUID

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, status

from api.auth.dependencies import get_current_user_id
from api.users.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from api.auth.service import (
    create_access_token,
    hash_password,
    verify_password,
)
from api.database import get_db_connection


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: RegisterRequest,
    db=Depends(get_db_connection),
):
    email = data.email.lower().strip()

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM users
            WHERE email = %s
            """,
            (email,),
        )

        existing_user = cursor.fetchone()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        password_hash_value = hash_password(
            data.password
        )

        cursor.execute(
            """
            INSERT INTO users (
                email,
                password_hash,
                name
            )
            VALUES (%s, %s, %s)
            RETURNING id, email, name, is_active
            """,
            (
                email,
                password_hash_value,
                data.name.strip(),
            ),
        )

        user = cursor.fetchone()

    db.commit()

    return UserResponse(
        id=str(user[0]),
        email=user[1],
        name=user[2],
        is_active=user[3],
    )


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
    db=Depends(get_db_connection),
):
    email = data.email.lower().strip()

    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                email,
                password_hash,
                is_active
            FROM users
            WHERE email = %s
            """,
            (email,),
        )

        user = cursor.fetchone()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    user_id, user_email, password_hash_value, is_active = user

    if not verify_password(
        data.password,
        password_hash_value,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    token = create_access_token(user_id)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user_id: Annotated[
        UUID,
        Depends(get_current_user_id),
    ],
    db=Depends(get_db_connection),
):
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                id,
                email,
                name,
                is_active
            FROM users
            WHERE id = %s
            """,
            (str(current_user_id),),
        )

        user = cursor.fetchone()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse(
        id=str(user[0]),
        email=user[1],
        name=user[2],
        is_active=user[3],
    )