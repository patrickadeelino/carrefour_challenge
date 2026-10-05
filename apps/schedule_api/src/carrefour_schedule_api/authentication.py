"""JWT authentication dependencies for the HTTP API."""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)


def get_authenticated_subject(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    if credentials is None:
        raise _unauthorized()

    try:
        claims = jwt.decode(
            credentials.credentials,
            request.app.state.settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except jwt.InvalidTokenError as error:
        raise _unauthorized() from error

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise _unauthorized()
    return subject


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_or_missing_bearer_token"},
        headers={"WWW-Authenticate": "Bearer"},
    )
