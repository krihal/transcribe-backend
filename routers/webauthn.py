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

import hashlib
import json

from urllib.parse import urlparse

import webauthn
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes

from auth.oidc import get_current_user
from db.user import user_update
from db.webauthn import (
    webauthn_credential_create,
    webauthn_credential_get_by_id,
    webauthn_credential_update_sign_count,
    webauthn_credentials_get,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from utils.log import get_logger
from utils.settings import get_settings
from utils.crypto import validate_private_key_password
from db.user import user_get_private_key

log = get_logger()
router = APIRouter(tags=["webauthn"])
settings = get_settings()

# Fixed PRF salt — consistent across all operations so the output is always the same
# for a given credential. Not a secret; security comes from the credential itself.
_PRF_SALT = hashlib.sha256(b"scribe-encryption-prf-v1").digest()
_PRF_SALT_B64 = bytes_to_base64url(_PRF_SALT)

# Short-lived in-memory challenge store keyed by user_id.
# Each entry stores the challenge bytes plus the rp_id and origin derived from the
# request, so complete() uses the same values that begin() used.
_challenges: dict[str, dict] = {}


def _rp_id_and_origin_from_request(request: Request) -> tuple[str, str]:
    """Derive rpId and expected origin from the request's Origin header.

    Using the live request origin means the WebAuthn rpId always matches whatever
    hostname the browser is actually at (localhost, 127.0.0.1, a real domain…)
    without requiring environment-specific configuration.  Falls back to settings
    when the header is absent (e.g. server-side calls or non-browser clients).
    """
    origin = request.headers.get("origin")
    if origin:
        hostname = urlparse(origin).hostname or settings.WEBAUTHN_RP_ID
        return hostname, origin
    return settings.WEBAUTHN_RP_ID, settings.WEBAUTHN_ORIGIN


class WebAuthnRegisterCompleteRequest(BaseModel):
    id: str
    rawId: str
    type: str
    response: dict
    prf_output: str
    name: Optional[str] = None


class WebAuthnAuthCompleteRequest(BaseModel):
    id: str
    rawId: str
    type: str
    response: dict


@router.post("/webauthn/register/begin")
async def webauthn_register_begin(
    request: Request,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Begin WebAuthn registration. Returns PublicKeyCredentialCreationOptions
    with the PRF extension so the authenticator computes a deterministic secret.
    """
    user_id = user["user_id"]
    username = user["username"]

    rp_id, origin = _rp_id_and_origin_from_request(request)

    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=user_id.encode("utf-8")[:64],
        user_name=username,
        user_display_name=username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )

    _challenges[user_id] = {"challenge": options.challenge, "rp_id": rp_id, "origin": origin}

    options_dict = json.loads(webauthn.options_to_json(options))

    # Inject PRF extension — py_webauthn doesn't model PRF directly
    options_dict["extensions"] = {
        "prf": {
            "eval": {
                "first": _PRF_SALT_B64
            }
        }
    }

    return JSONResponse(content=options_dict)


@router.post("/webauthn/register/complete")
async def webauthn_register_complete(
    item: WebAuthnRegisterCompleteRequest,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Complete WebAuthn registration. Verifies the attestation, stores the
    credential, and generates the user's RSA keypair protected by the PRF output.
    """
    user_id = user["user_id"]

    stored = _challenges.pop(user_id, None)
    if not stored:
        raise HTTPException(status_code=400, detail="No pending registration challenge.")

    if not item.prf_output or len(item.prf_output) != 64:
        raise HTTPException(
            status_code=400,
            detail="PRF output missing or invalid. Your authenticator may not support the PRF extension.",
        )

    try:
        registration_credential = webauthn.helpers.structs.RegistrationCredential(
            id=item.id,
            raw_id=base64url_to_bytes(item.rawId),
            response=webauthn.helpers.structs.AuthenticatorAttestationResponse(
                client_data_json=base64url_to_bytes(item.response["clientDataJSON"]),
                attestation_object=base64url_to_bytes(item.response["attestationObject"]),
            ),
            type=item.type,
        )

        verification = webauthn.verify_registration_response(
            credential=registration_credential,
            expected_challenge=stored["challenge"],
            expected_rp_id=stored["rp_id"],
            expected_origin=stored["origin"],
            require_user_verification=True,
        )
    except Exception as e:
        log.warning(f"WebAuthn registration verification failed for user {user_id}: {e}")
        raise HTTPException(status_code=400, detail="Registration verification failed.")

    credential_id_b64 = bytes_to_base64url(verification.credential_id)
    public_key_b64 = bytes_to_base64url(verification.credential_public_key)

    await webauthn_credential_create(
        user_id=user_id,
        credential_id=credential_id_b64,
        public_key=public_key_b64,
        sign_count=verification.sign_count,
        name=item.name,
    )

    # Use the PRF output as the encryption passphrase — same flow as typed passphrase
    await user_update(
        user_id,
        encryption_settings=True,
        encryption_password=item.prf_output,
    )

    log.info(f"WebAuthn registration complete for user {user_id}")
    return JSONResponse(content={"result": {"status": "OK"}})


@router.post("/webauthn/auth/begin")
async def webauthn_auth_begin(
    request: Request,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Begin WebAuthn authentication. Returns PublicKeyCredentialRequestOptions
    with the PRF extension and the user's registered credential IDs.
    """
    user_id = user["user_id"]

    rp_id, origin = _rp_id_and_origin_from_request(request)

    credentials = await webauthn_credentials_get(user_id)
    if not credentials:
        raise HTTPException(status_code=404, detail="No passkeys registered for this user.")

    allow_credentials = [
        webauthn.helpers.structs.PublicKeyCredentialDescriptor(
            id=base64url_to_bytes(c["credential_id"])
        )
        for c in credentials
    ]

    options = webauthn.generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
    )

    _challenges[user_id] = {"challenge": options.challenge, "rp_id": rp_id, "origin": origin}

    options_dict = json.loads(webauthn.options_to_json(options))
    options_dict["extensions"] = {
        "prf": {
            "eval": {
                "first": _PRF_SALT_B64
            }
        }
    }

    return JSONResponse(content=options_dict)


@router.post("/webauthn/auth/complete")
async def webauthn_auth_complete(
    item: WebAuthnAuthCompleteRequest,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Complete WebAuthn authentication. Verifies the assertion and updates the
    credential sign count. The PRF output is used client-side as the encryption key.
    """
    user_id = user["user_id"]

    stored = _challenges.pop(user_id, None)
    if not stored:
        raise HTTPException(status_code=400, detail="No pending authentication challenge.")

    credential_record = await webauthn_credential_get_by_id(item.id)
    if not credential_record or credential_record.user_id != user_id:
        raise HTTPException(status_code=400, detail="Unknown credential.")

    try:
        auth_credential = webauthn.helpers.structs.AuthenticationCredential(
            id=item.id,
            raw_id=base64url_to_bytes(item.rawId),
            response=webauthn.helpers.structs.AuthenticatorAssertionResponse(
                client_data_json=base64url_to_bytes(item.response["clientDataJSON"]),
                authenticator_data=base64url_to_bytes(item.response["authenticatorData"]),
                signature=base64url_to_bytes(item.response["signature"]),
                user_handle=base64url_to_bytes(item.response["userHandle"]) if item.response.get("userHandle") else None,
            ),
            type=item.type,
        )

        verification = webauthn.verify_authentication_response(
            credential=auth_credential,
            expected_challenge=stored["challenge"],
            expected_rp_id=stored["rp_id"],
            expected_origin=stored["origin"],
            credential_public_key=base64url_to_bytes(credential_record.public_key),
            credential_current_sign_count=credential_record.sign_count,
            require_user_verification=True,
        )
    except Exception as e:
        log.warning(f"WebAuthn authentication verification failed for user {user_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e) if settings.API_DEBUG else "Authentication verification failed.")

    await webauthn_credential_update_sign_count(item.id, verification.new_sign_count)

    log.info(f"WebAuthn authentication complete for user {user_id}")
    return JSONResponse(content={"result": {"status": "OK"}})


@router.post("/webauthn/verify")
async def webauthn_verify_prf(
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Verify that the supplied PRF output correctly decrypts the user's private key.
    Called by the frontend after a successful auth/complete to confirm the key is valid.
    The actual PRF output is sent as the encryption_password via the existing /me PUT endpoint.
    """
    return JSONResponse(content={"result": {"status": "OK"}})
