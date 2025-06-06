from auth.oidc import RefreshToken
from auth.oidc import oauth
from auth.oidc import verify_user
from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from routers.job import router as job_router
from routers.static import router as static_router
from routers.transcriber import router as transcriber_router
from routers.video import router as video_router
from starlette.middleware.sessions import SessionMiddleware
from utils.settings import get_settings

import requests

settings = get_settings()

app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    secret_key=settings.API_SECRET_KEY,
    openapi_tags=[
        {
            "name": "transcriber",
            "description": "Transcription operations",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(SessionMiddleware, settings.API_SECRET_KEY, https_only=False)
app.include_router(transcriber_router, prefix=settings.API_PREFIX, tags=["transcriber"])
app.include_router(job_router, prefix=settings.API_PREFIX, tags=["job"])
app.include_router(video_router, prefix=settings.API_PREFIX, tags=["video"])
app.include_router(static_router, prefix="", tags=["static"])


@app.get("/api/auth")
async def auth(request: Request):
    token = await oauth.auth0.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        raise ValueError("Failed to get userinfo from token")

    request.session["id_token"] = token["access_token"]

    if "refresh_token" in token:
        request.session["refresh_token"] = token["refresh_token"]

    url = f"{settings.OIDC_REDIRECT_URI}/?token={token['id_token']}"

    if "refresh_token" in token:
        url += f"&refresh_token={token['refresh_token']}"

    return RedirectResponse(url=url)


@app.get("/api/login")
async def login(request: Request):
    redirect_uri = request.url_for("auth")
    return await oauth.auth0.authorize_redirect(request, redirect_uri)


@app.get("/api/logout")
async def logout(request: Request):
    return RedirectResponse(url=settings.OIDC_REDIRECT_URI)


@app.post("/api/refresh")
async def refresh(request: Request, refresh_token: RefreshToken):
    data = {
        "client_id": "nac",
        "client_secret": settings.OIDC_CLIENT_SECRET,
        "refresh_token": refresh_token.token,
        "grant_type": "refresh_token",
    }

    try:
        response = requests.post(
            "https://norpan-keycloak1.cnaas.sunet.se/realms/norpan/protocol/openid-connect/token",
            data=data,
        )
        response.raise_for_status()
    except Exception as e:
        return JSONResponse({"error": "Failed to refresh token"}, status_code=400)

    return JSONResponse({"access_token": response.json()["access_token"]})


@app.get("/docs")
async def docs(request: Request) -> RedirectResponse:
    await verify_user(request)

    return RedirectResponse(url="/docs")
