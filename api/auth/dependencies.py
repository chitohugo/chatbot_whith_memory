from typing import Annotated
from uuid import UUID
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from api.auth.service import decode_access_token
from api.database import get_db_session
from api.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user_id(token: Annotated[str, Depends(oauth2_scheme)], db=Depends(get_db_session)) -> UUID:
    invalid = HTTPException(401, "Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        user_id = UUID(decode_access_token(token)["sub"])
    except (InvalidTokenError, ValueError, TypeError, KeyError) as error:
        raise invalid from error
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise invalid
    return user_id
