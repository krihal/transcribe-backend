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

from typing import List, Optional

from sqlalchemy import select

from db.models import WebAuthnCredential
from db.session import get_async_session
from utils.log import get_logger

log = get_logger()


async def webauthn_credential_create(
    user_id: str,
    credential_id: str,
    public_key: str,
    sign_count: int,
    name: Optional[str] = None,
) -> dict:
    async with get_async_session() as session:
        credential = WebAuthnCredential(
            user_id=user_id,
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            name=name,
        )
        session.add(credential)
        await session.commit()
        await session.refresh(credential)
        log.info(f"Stored WebAuthn credential for user {user_id}")
        return credential.as_dict()


async def webauthn_credentials_get(user_id: str) -> List[dict]:
    async with get_async_session() as session:
        result = await session.execute(
            select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
        )
        credentials = result.scalars().all()
        return [c.as_dict() for c in credentials]


async def webauthn_credential_get_by_id(credential_id: str) -> Optional[WebAuthnCredential]:
    async with get_async_session() as session:
        result = await session.execute(
            select(WebAuthnCredential).where(WebAuthnCredential.credential_id == credential_id)
        )
        return result.scalars().first()


async def webauthn_credential_update_sign_count(credential_id: str, sign_count: int) -> None:
    async with get_async_session() as session:
        result = await session.execute(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.credential_id == credential_id)
            .with_for_update()
        )
        credential = result.scalars().first()
        if credential:
            credential.sign_count = sign_count
            await session.commit()


async def webauthn_credentials_delete(user_id: str) -> None:
    async with get_async_session() as session:
        result = await session.execute(
            select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
        )
        credentials = result.scalars().all()
        for credential in credentials:
            await session.delete(credential)
        await session.commit()
        log.info(f"Deleted all WebAuthn credentials for user {user_id}")


async def webauthn_has_credentials(user_id: str) -> bool:
    async with get_async_session() as session:
        result = await session.execute(
            select(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
        )
        return result.scalars().first() is not None
