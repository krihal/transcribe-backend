# Copyright (c) 2025-2026 Sunet.
# Contributor: Kristofer Hallin
#
# This file is part of Sunet Scribe.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from authlib.integrations.starlette_client import OAuth
from authlib.jose import jwt
from datetime import datetime
from db.user import user_create
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from typing import Optional
from utils.log import get_logger
from utils.settings import get_settings

log = get_logger()
settings = get_settings()

oauth = OAuth()
oauth.register(
    name="auth0",
    server_metadata_url=settings.OIDC_METADATA_URL,
    client_id=settings.OIDC_CLIENT_ID,
    client_secret=settings.OIDC_CLIENT_SECRET,
    client_kwargs={"scope": "openid profile email"},
    redirect_uri=settings.OIDC_REDIRECT_URI,
)


async def get_current_admin_user(request: Request) -> str:
    """
    Get the current admin user from the request.

    1. Verify the user.
    2. Check if the user is an admin.
    3. Return the user ID.

    Parameters:
        request (Request): The incoming HTTP request.

    Returns:
        str: The current admin user ID.
    """

    user = await verify_user(request, admin=True)

    log.info(f"User {user["user_id"]} was granted admin access.")

    return user


async def get_current_user(request: Request) -> str:
    """
    Get the current user from the request.

    1. Verify the user.
    2. Return the user ID.

    Parameters:
        request (Request): The incoming HTTP request.

    Returns:
        str: The current user ID.
    """

    return await verify_user(request)


class UnauthenticatedError(HTTPException):
    """
    Exception raised when the user is not authenticated.

    Parameters:
        error (Optional[str]): Additional error message.

    Raises:
        HTTPException: 401 Unauthorized with the error message.

    Returns:
        None
    """

    def __init__(self, error: Optional[str] = "") -> None:
        """
        Initialize the exception.

        Parameters:
            error (Optional[str]): Additional error message.

        Raises:
            HTTPException: 401 Unauthorized with the error message.
        """
        super().__init__(status_code=401, detail="You are not authenticated: " + error)


class RefreshToken(BaseModel):
    """
    Refresh token model.

    Parameters:
        token (str): The refresh token.
    """

    token: str


async def verify_token(id_token: str) -> dict:
    """
    Verify the given ID token.
    1. Fetch the JWKS from the OIDC provider.
    2. Decode and verify the JWT using the JWKS.
    3. Check the issuer and expiration time.

    Parameters:
        id_token (str): The ID token to verify.

    Returns:
        dict: The decoded JWT payload.
    """

    # Fetch the JWKS from the OIDC provider
    jwks = await oauth.auth0.fetch_jwk_set()

    # Decode and verify the JWT
    try:
        decoded_jwt = jwt.decode(s=id_token, key=jwks)
    except Exception as e:
        raise UnauthenticatedError("Invalid token.") from e

    # Validate issuer and expiration
    metadata = await oauth.auth0.load_server_metadata()

    # Validate issuer
    if decoded_jwt["iss"] != metadata["issuer"]:
        raise UnauthenticatedError("Invalid issuer.")

    # Check if the token is expired
    if datetime.fromtimestamp(decoded_jwt["exp"]) < datetime.now():
        raise UnauthenticatedError("Token expired.")

    return decoded_jwt


async def verify_user(request: Request, admin: Optional[bool] = False) -> str:
    """
    Verify the user from the request.
    1. Extract the ID token from the Authorization header.
    2. Verify the ID token.
    3. Create or update the user in the database.
    4. Return the user ID.

    Parameters:
        request (Request): The incoming HTTP request.

    Returns:
        str: The verified user ID.
    """

    # Check if the Authorization header is present
    if not (auth_header := request.headers.get("Authorization")):
        raise UnauthenticatedError("No authorization header found.")

    # Check if the Authorization header is in the correct format
    if not auth_header.startswith("Bearer "):
        raise UnauthenticatedError("Invalid authorization header format.")

    # Extract the ID token
    if not (id_token := auth_header.split(" ")[1]):
        raise UnauthenticatedError("No id_token found.")

    decoded_jwt = await verify_token(id_token=id_token)

    # Create or update the user in the database
    user_id = decoded_jwt["sub"]
    username = decoded_jwt.get("preferred_username")
    realm = decoded_jwt.get("realm", username.split("@")[-1])

    user = await user_create(
        username=username,
        realm=realm,
        user_id=user_id,
        email=decoded_jwt.get("email", ""),
    )

    # Check if the user is active
    if not user["active"]:
        log.info(f"User {user_id} is not active.")
        raise HTTPException(status_code=403, detail="User is not active.")

    if admin and not user["admin"]:
        log.error(f"User {user_id} is not an admin.")
        raise HTTPException(status_code=403, detail="User is not an admin.")

    if not admin:
        log.info(f"User {user_id} authenticated successfully.")

    return user
