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
#

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from db.user import (
    user_delete,
    user_get,
    users_statistics,
    user_get_all,
    user_update,
    group_statistics,
)
from db.group import (
    group_get,
    group_get_all,
    group_create,
    group_update,
    group_delete,
    group_add_user,
    group_remove_user,
)

from utils.log import get_logger

from utils.settings import get_settings
from auth.oidc import (
    get_current_user,
    get_current_admin_user,
)

from utils.validators import (
    ModifyUserRequest,
    CreateGroupRequest,
    UpdateGroupRequest,
)

log = get_logger()
router = APIRouter(tags=["admin"])
settings = get_settings()


def _get_admin_allowed_realms(admin_user: dict) -> list[str]:
    """
    Return the list of realms a non-BOFH admin may manage.

    Parameters:
        admin_user (dict): The admin user dict.

    Returns:
        list[str]: The list of allowed realms.
    """

    realms = set()

    if admin_user.get("realm"):
        realms.add(admin_user["realm"])

    for d in (admin_user.get("admin_domains") or "").split(","):
        d = d.strip()
        if d:
            realms.add(d)
    return sorted(realms)


@router.get("/admin")
async def statistics(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Get user statistics.
    Used by the frontend to get user statistics.

    Parameters:
        request (Request): The incoming HTTP request.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The user statistics.
    """

    if admin_user["bofh"]:
        realm = "*"
    else:
        admin_domains = admin_user.get("admin_domains", "") or ""
        realms = [d.strip() for d in admin_domains.split(",") if d.strip()]
        realm = realms if realms else [admin_user["realm"]]

    return JSONResponse(content={"result": await users_statistics(realm=realm)})


@router.get("/admin/users")
async def list_users(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    List all users with statistics.
    Used by the frontend to list all users.

    Parameters:
        request (Request): The incoming HTTP request.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The list of users with statistics.
    """

    if admin_user["bofh"]:
        realms = "*"
    else:
        admin_domains = admin_user.get("admin_domains", "") or ""
        realms = [d.strip() for d in admin_domains.split(",") if d.strip()]
        if not realms:
            realms = [admin_user["realm"]]

    return JSONResponse(content={"result": await user_get_all(realm=realms)})


@router.put("/admin/{username}")
async def modify_user(
    request: Request,
    item: ModifyUserRequest,
    username: str,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Modify a user's active status.
    Used by the frontend to modify a user's active status.

    Parameters:
        request (Request): The incoming HTTP request.
        username (str): The username of the user to modify.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The result of the operation.
    """
    target_user = await user_get(username=username)
    if not target_user or not target_user.get("user_id"):
        return JSONResponse(
            content={"error": "User not found"},
            status_code=404,
        )

    if not admin_user["bofh"]:
        admin_domains = admin_user.get("admin_domains", "") or ""
        allowed_realms = [d.strip() for d in admin_domains.split(",") if d.strip()]
        if not allowed_realms:
            allowed_realms = [admin_user["realm"]]
        if target_user.get("realm") not in allowed_realms:
            log.warning(
                f"Admin {admin_user['user_id']} denied modify access to user (realm mismatch)"
            )
            return JSONResponse(
                content={"error": "Not authorized to modify this user"},
                status_code=403,
            )

    user_id = target_user["user_id"]

    if item.active is not None:
        await user_update(
            user_id,
            active=item.active,
        )

    if item.admin is not None:
        await user_update(
            user_id,
            admin=item.admin,
        )

    if item.admin_domains is not None:
        await user_update(
            user_id,
            admin_domains=item.admin_domains,
        )

    if item.reset_manual:
        await user_update(
            user_id,
            reset_manual=True,
        )

    return JSONResponse(content={"result": {"status": "OK"}})


@router.delete("/admin/{username}")
async def delete_user(
    request: Request,
    username: str,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Soft-delete a user. The user is marked as deleted and will be
    permanently removed once all associated job data has been cleaned up.

    Parameters:
        request (Request): The incoming HTTP request.
        username (str): The username of the user to delete.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The result of the operation.
    """

    if not admin_user["bofh"]:
        target_user = await user_get(username=username)
        if not target_user or not target_user.get("user_id"):
            return JSONResponse(
                content={"error": "User not found"},
                status_code=404,
            )
        admin_domains = admin_user.get("admin_domains", "") or ""
        allowed_realms = [d.strip() for d in admin_domains.split(",") if d.strip()]
        if not allowed_realms:
            allowed_realms = [admin_user["realm"]]
        if target_user.get("realm") not in allowed_realms:
            log.warning(
                f"Admin {admin_user['user_id']} denied delete access to user (realm mismatch)"
            )
            return JSONResponse(
                content={"error": "Not authorized to delete this user"},
                status_code=403,
            )

    if not await user_delete(username):
        return JSONResponse(
            content={"error": "User not found"},
            status_code=404,
        )

    return JSONResponse(content={"result": {"status": "OK"}})


@router.get("/admin/groups")
async def list_groups(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    List all groups with statistics and member counts.

    Parameters:
        request (Request): The incoming HTTP request.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The list of groups with statistics and member counts.
    """

    if admin_user["bofh"]:
        realm = "*"
    else:
        realm = admin_user["realm"]

    groups = await group_get_all(admin_user["user_id"], realm=realm)
    result = []

    for g in groups:
        stats = await group_statistics(g["id"], admin_user["user_id"], realm)

        if g["name"] == "All users":
            g["nr_users"] = stats["total_users"]

        group_dict = {
            "id": g["id"],
            "name": g["name"],
            "customer_name": g.get("customer_name", "None"),
            "realm": g["realm"],
            "description": g["description"],
            "created_at": g["created_at"],
            "users": g["users"],
            "nr_users": stats["total_users"],
            "stats": stats,
            "quota_seconds": g["quota_seconds"],
        }

        result.append(group_dict)

    return JSONResponse(content={"result": result})


@router.post("/admin/groups")
async def create_group(
    request: Request,
    item: CreateGroupRequest,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Create a new group.

    Parameters:
        request (Request): The incoming HTTP request.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The result of the operation.
    """

    if not item.name:
        return JSONResponse(content={"error": "Missing group name"}, status_code=400)

    group = await group_create(
        name=item.name,
        realm=admin_user["realm"],
        description=item.description,
        quota_seconds=item.quota_seconds,
        owner_user_id=admin_user["user_id"],
    )

    if not group:
        return JSONResponse(
            content={"error": "Failed to create group"}, status_code=500
        )

    return JSONResponse(content={"result": {"id": group["id"], "name": group["name"]}})


@router.get("/admin/groups/{group_id}")
async def get_group(
    request: Request,
    group_id: int,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Get group details.

    Parameters:
        request (Request): The incoming HTTP request.
        group_id (str): The ID of the group.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The group details.
    """

    if admin_user["bofh"]:
        realm = "*"
    else:
        realm = admin_user["realm"]

    group = await group_get(group_id, realm=realm, user_id=admin_user["user_id"])

    if not group:
        return JSONResponse(content={"error": "Group not found"}, status_code=404)

    return JSONResponse(content={"result": group})


@router.put("/admin/groups/{group_id}")
async def update_group(
    request: Request,
    item: UpdateGroupRequest,
    group_id: int,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Update group details (name/description).

    Parameters:
        request (Request): The incoming HTTP request.
        group_id (int): The ID of the group.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The result of the operation.
    """

    if admin_user["bofh"]:
        realm = "*"
    else:
        realm = admin_user["realm"]

    group = await group_get(group_id, realm=realm, user_id=admin_user["user_id"])
    if not group:
        return JSONResponse(content={"error": "Group not found"}, status_code=404)

    try:
        if not await group_update(
            group_id,
            name=item.name,
            description=item.description,
            usernames=item.usernames,
            quota_seconds=int(item.quota),
        ):
            return JSONResponse(content={"error": "Group not found"}, status_code=404)
    except ValueError as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

    return JSONResponse(content={"result": {"status": "ok"}})


@router.delete("/admin/groups/{group_id}")
async def delete_group(
    request: Request,
    group_id: int,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Delete a group.

    Parameters:
        request (Request): The incoming HTTP request.
        group_id (int): The ID of the group.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The result of the operation.
    """

    if admin_user["bofh"]:
        realm = "*"
    else:
        realm = admin_user["realm"]

    group = await group_get(group_id, realm=realm, user_id=admin_user["user_id"])
    if not group:
        return JSONResponse(content={"error": "Group not found"}, status_code=404)

    if not await group_delete(group_id):
        return JSONResponse(content={"error": "Group not found"}, status_code=404)

    return JSONResponse(content={"result": {"status": "OK"}})


@router.post("/admin/groups/{group_id}/users/{username}")
async def add_user_to_group(
    request: Request,
    group_id: int,
    username: str,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Add a user to a group.

    Parameters:
        request (Request): The incoming HTTP request.
        group_id (int): The ID of the group.
        username (str): The username of the user to add.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The result of the operation.
    """

    if admin_user["bofh"]:
        realm = "*"
    else:
        realm = admin_user["realm"]

    group = await group_get(group_id, realm=realm, user_id=admin_user["user_id"])
    if not group:
        return JSONResponse(content={"error": "Group not found"}, status_code=404)

    if not await group_add_user(group_id, username):
        return JSONResponse(
            content={"error": "User or group not found"}, status_code=404
        )

    return JSONResponse(content={"result": {"status": "OK"}})


@router.delete("/admin/groups/{group_id}/users/{username}")
async def remove_user_from_group(
    request: Request,
    group_id: int,
    username: str,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Remove a user from a group.

    Parameters:
        admin_user (dict): The current user.
        request (Request): The incoming HTTP request.
        group_id (int): The ID of the group.
        username (str): The username of the user to remove.

    Returns:
        JSONResponse: The result of the operation.
    """

    if admin_user["bofh"]:
        realm = "*"
    else:
        realm = admin_user["realm"]

    group = await group_get(group_id, realm=realm, user_id=admin_user["user_id"])
    if not group:
        return JSONResponse(content={"error": "Group not found"}, status_code=404)

    if not await group_remove_user(group_id, username):
        return JSONResponse(
            content={"error": "User or group not found"}, status_code=404
        )

    return JSONResponse(content={"result": {"status": "OK"}})


@router.get("/admin/groups/{group_id}/stats")
async def group_stats(
    request: Request,
    group_id: int,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Get group statistics.

    Parameters:
        request (Request): The incoming HTTP request.
        group_id (int): The ID of the group.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The group statistics.
    """

    if admin_user["bofh"]:
        realm = "*"
    else:
        realm = admin_user["realm"]

    group = await group_get(group_id, realm=realm, user_id=admin_user["user_id"])

    if not group:
        return JSONResponse(content={"error": "Group not found"}, status_code=404)

    return JSONResponse(
        content={
            "result": await users_statistics(
                group_id, realm=realm, user_id=admin_user["user_id"]
            )
        }
    )
