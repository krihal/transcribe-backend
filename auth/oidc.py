from fastapi import Request
from authlib.jose import jwt
from fastapi import HTTPException
from datetime import datetime
from utils.settings import get_settings
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel

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


class UnauthenticatedError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=401, detail="You are not authenticated.")


class RefreshToken(BaseModel):
    token: str


async def verify_token(id_token: str):
    jwks = await oauth.auth0.fetch_jwk_set()
    try:
        decoded_jwt = jwt.decode(s=id_token, key=jwks)
    except Exception as e:
        raise UnauthenticatedError("Invalid token.") from e

    metadata = await oauth.auth0.load_server_metadata()

    if decoded_jwt["iss"] != metadata["issuer"]:
        raise UnauthenticatedError("Invalid issuer.")

    exp = datetime.fromtimestamp(decoded_jwt["exp"])
    if exp < datetime.now():
        raise UnauthenticatedError("Token expired.")
    return decoded_jwt


async def verify_user(request: Request):
    auth_header = request.headers.get("Authorization")

    if auth_header is None:
        raise UnauthenticatedError("No authorization header found.")

    if not auth_header.startswith("Bearer "):
        raise UnauthenticatedError("Invalid authorization header format.")

    id_token = auth_header.split(" ")[1]

    if id_token is None:
        raise UnauthenticatedError("No id_token found.")

    decoded_jwt = await verify_token(id_token=id_token)
    user_id = decoded_jwt["sub"]

    return user_id
