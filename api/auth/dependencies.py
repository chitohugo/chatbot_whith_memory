from secrets import compare_digest
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError

from api.auth.service import decode_access_token
from api.database import get_db_connection
from config import settings


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
)


def get_current_user_id(
    token: Annotated[str, Depends(oauth2_scheme)],
    db=Depends(get_db_connection),
) -> UUID:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )

    try:
        payload = decode_access_token(token)

        user_id = payload.get("sub")

        if not user_id:
            raise credentials_exception

        parsed_user_id = UUID(user_id)
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM users
                WHERE id = %s AND is_active = TRUE
                """,
                (str(parsed_user_id),),
            )
            if cursor.fetchone() is None:
                raise credentials_exception

        return parsed_user_id

    except (
        InvalidTokenError,
        ValueError,
    ) as exc:
        raise credentials_exception from exc


def require_internal_request(
    internal_request: Annotated[
        str | None,
        Header(alias="X-Internal-Request"),
    ] = None,
) -> None:
    if internal_request is None or not compare_digest(
        internal_request,
        settings.auth.secret_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal request required",
        )