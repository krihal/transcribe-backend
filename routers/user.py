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

from auth.oidc import get_current_user
from db.announcement import announcement_get_active
from db.user import (
    user_get_private_key,
    user_update,
)

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from utils.log import get_logger
from utils.settings import get_settings
from utils.crypto import validate_private_key_password
from utils.validators import UserUpdateRequest

log = get_logger()
router = APIRouter(tags=["user"])
settings = get_settings()

api_file_storage_dir = settings.API_FILE_STORAGE_DIR


@router.get("/me")
async def get_user_info(
    request: Request,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Get user information.
    Used by the frontend to get user information.

    Parameters:
        request (Request): The incoming HTTP request.
        user (dict): The current user.

    Returns:
        JSONResponse: The user information.
    """

    result = dict(user)
    result["announcements"] = await announcement_get_active()
    return JSONResponse(content={"result": result})


@router.put("/me")
async def set_user_info(
    item: UserUpdateRequest,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Set user information.
    Used by the frontend to set user information.

    Parameters:
        item (UserUpdateRequest): The user update data.
        user (dict): The current user.

    Returns:
        JSONResponse:  The result of the operation.
    """

    if item.encryption and item.encryption_password:
        await user_update(
            user["user_id"],
            encryption_settings=item.encryption,
            encryption_password=item.encryption_password,
        )
    elif item.reset_password:
        await user_update(user["user_id"], reset_encryption=True)
    elif item.verify_password:
        private_key = await user_get_private_key(user["user_id"])

        try:
            validate_private_key_password(private_key, item.encryption_password)
        except ValueError:
            log.info(
                f"Invalid private key password for user {user["user_id"]}"
            )
            return JSONResponse(
                content={"error": "Invalid private key or password"},
                status_code=403,
            )
    elif item.email is not None:
        await user_update(user["user_id"], email=item.email)
    elif item.notifications:
        notifications_str = ""

        if (
            item.notifications.notify_on_job is not None
            and item.notifications.notify_on_job
        ):
            notifications_str += "job,"
        if (
            item.notifications.notify_on_deletion is not None
            and item.notifications.notify_on_deletion
        ):
            notifications_str += "deletion,"
        if (
            item.notifications.notify_on_user is not None
            and item.notifications.notify_on_user
        ):
            notifications_str += "user,"
        if (
            item.notifications.notify_on_quota is not None
            and item.notifications.notify_on_quota
        ):
            notifications_str += "quota,"
        if (
            item.notifications.notify_on_weekly_report is not None
            and item.notifications.notify_on_weekly_report
        ):
            notifications_str += "weekly_report,"

        await user_update(user["user_id"], notifications_str=notifications_str)
    elif item.dark_mode != "UNSET":
        await user_update(user["user_id"], dark_mode=item.dark_mode)

    return JSONResponse(content={"result": {"status": "OK"}})


