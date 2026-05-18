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
from db.attribute_rules import (
    rule_create,
    rule_get,
    rule_get_all,
    rule_update,
    rule_delete,
    test_rules,
)
from db.onboarding_attributes import (
    attribute_get_all,
    attribute_add,
    attribute_delete,
)

from utils.log import get_logger

from auth.oidc import get_current_admin_user

from utils.validators import (
    CreateAttributeRuleRequest,
    UpdateAttributeRuleRequest,
    CreateOnboardingAttributeRequest,
    TestRulesRequest,
)

log = get_logger()
router = APIRouter(tags=["admin"])


def _get_admin_allowed_realms(admin_user: dict) -> list[str]:
    """
    Return the list of realms a non-BOFH admin may manage rules for.

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


def _rule_realm_overlaps(rule_realm: str | None, allowed: list[str]) -> bool:
    """
    Check if any of the rule's comma-separated realms overlap with allowed.

    Parameters:
        rule_realm (str | None): The rule's realm(s) as a comma-separated string.

    Returns:
        bool: True if any realm overlaps with allowed, False otherwise.
    """

    if not rule_realm:
        return False

    rule_realms = {r.strip() for r in rule_realm.split(",") if r.strip()}

    return bool(rule_realms & set(allowed))


@router.get("/admin/rules", include_in_schema=False)
async def list_rules(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    List all attribute rules.

    Parameters:
        request (Request): The incoming HTTP request.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The list of attribute rules.
    """

    if admin_user["bofh"]:
        realm = "*"
    else:
        realm = _get_admin_allowed_realms(admin_user)

    return JSONResponse(content={"result": await rule_get_all(realm=realm)})


@router.post("/admin/rules")
async def create_rule(
    request: Request,
    item: CreateAttributeRuleRequest,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Create a new attribute rule.
    """

    if not item.name or not item.attribute_name or not item.attribute_value:
        return JSONResponse(
            content={"error": "Missing required fields"}, status_code=400
        )

    if admin_user["bofh"]:
        realm = item.realm
    else:
        allowed = _get_admin_allowed_realms(admin_user)
        realm = item.realm if item.realm in allowed else allowed[0]

    rule = await rule_create(
        name=item.name,
        attribute_name=item.attribute_name,
        attribute_condition=item.attribute_condition,
        attribute_value=item.attribute_value,
        realm=realm,
        activate=item.activate,
        admin=item.admin,
        deny=item.deny,
        assign_to_group=item.assign_to_group,
        notify_job=item.notify_job,
        notify_deletion=item.notify_deletion,
        owner_domains=item.owner_domains,
        enabled=item.enabled,
        user_id=admin_user["user_id"],
    )

    return JSONResponse(content={"result": rule})


@router.get("/admin/rules/{rule_id}")
async def get_rule(
    request: Request,
    rule_id: int,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Get a single attribute rule.
    """

    rule = await rule_get(rule_id)

    if not rule:
        return JSONResponse(content={"error": "Rule not found"}, status_code=404)

    if not admin_user["bofh"]:
        allowed = _get_admin_allowed_realms(admin_user)
        if not _rule_realm_overlaps(rule.get("realm"), allowed):
            log.warning(f"Admin {admin_user['user_id']} denied access to rule {rule_id} (realm mismatch)")
            return JSONResponse(content={"error": "Not authorized"}, status_code=403)

    return JSONResponse(content={"result": rule})


@router.put("/admin/rules/{rule_id}", include_in_schema=False)
async def update_rule_endpoint(
    request: Request,
    rule_id: int,
    item: UpdateAttributeRuleRequest,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Update an attribute rule.

    For non-BOFH admins, if the rule's realm(s) overlap with the admin's allowed realms,
    they can update the rule but cannot move it to a realm they don't manage.

    Parameters:
        request: The incoming HTTP request.
        rule_id: The ID of the rule to update.
        item: UpdateAttributeRuleRequest containing the updated rule details.
        admin_user: The current admin user.

    Returns:
        JSONResponse with the result of the operation.
    """

    if not admin_user["bofh"]:
        if not (existing := await rule_get(rule_id)):
            return JSONResponse(content={"error": "Rule not found"}, status_code=404)

        allowed = _get_admin_allowed_realms(admin_user)

        if not _rule_realm_overlaps(existing.get("realm"), allowed):
            log.warning(f"Admin {admin_user['user_id']} denied update access to rule {rule_id} (realm mismatch)")
            return JSONResponse(content={"error": "Not authorized"}, status_code=403)

        # Prevent non-BOFH from moving rule to a realm they don't manage
        if item.realm is not None:
            new_realms = {r.strip() for r in item.realm.split(",") if r.strip()}

            if not new_realms.issubset(set(allowed)):
                item.realm = existing["realm"]

    rule = await rule_update(
        rule_id,
        name=item.name,
        attribute_name=item.attribute_name,
        attribute_condition=item.attribute_condition,
        attribute_value=item.attribute_value,
        realm=item.realm,
        activate=item.activate,
        admin=item.admin,
        deny=item.deny,
        assign_to_group=item.assign_to_group,
        notify_job=item.notify_job,
        notify_deletion=item.notify_deletion,
        owner_domains=item.owner_domains,
        enabled=item.enabled,
        user_id=admin_user["user_id"],
    )

    if not rule:
        return JSONResponse(content={"error": "Rule not found"}, status_code=404)

    return JSONResponse(content={"result": rule})


@router.delete("/admin/rules/{rule_id}", include_in_schema=False)
async def delete_rule_endpoint(
    request: Request,
    rule_id: int,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Delete an attribute rule.

    Parameters:
        request: The incoming HTTP request.
        rule_id: The ID of the rule to delete.
        admin_user: The current admin user.

    Returns:
        JSONResponse with the result of the operation.
    """

    if not admin_user["bofh"]:
        if not (existing := await rule_get(rule_id)):
            return JSONResponse(content={"error": "Rule not found"}, status_code=404)

        allowed = _get_admin_allowed_realms(admin_user)

        if not _rule_realm_overlaps(existing.get("realm"), allowed):
            log.warning(f"Admin {admin_user['user_id']} denied delete access to rule {rule_id} (realm mismatch)")
            return JSONResponse(content={"error": "Not authorized"}, status_code=403)

    if not await rule_delete(rule_id, user_id=admin_user["user_id"]):
        return JSONResponse(content={"error": "Rule not found"}, status_code=404)

    return JSONResponse(content={"result": {"status": "OK"}})


@router.post("/admin/rules/test", include_in_schema=False)
async def test_rules_endpoint(
    request: Request,
    item: TestRulesRequest,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Test which users would be matched by the given rules.

    Parameters:
        request: The incoming HTTP request.
        item: TestRulesRequest containing the list of rule IDs to test.
        admin_user: The current admin user.

    Returns:
        JSONResponse with the list of matched users.
    """

    if not item.rule_ids:
        return JSONResponse(content={"error": "No rule IDs provided"}, status_code=400)

    if admin_user["bofh"]:
        realm = "*"
    else:
        allowed = _get_admin_allowed_realms(admin_user)
        realm = allowed

    matches = await test_rules(item.rule_ids, realm=realm)

    return JSONResponse(content={"result": matches})


@router.get("/admin/attributes", include_in_schema=False)
async def list_attributes(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    List all supported onboarding attributes.

    Parameters:
        request (Request): The incoming HTTP request.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The list of onboarding attributes.
    """

    return JSONResponse(content={"result": await attribute_get_all()})


@router.post("/admin/attributes", include_in_schema=False)
async def create_attribute(
    request: Request,
    item: CreateOnboardingAttributeRequest,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Add a new onboarding attribute. BOFH only.

    Parameters:
        request (Request): The incoming HTTP request.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The result of the operation.
    """

    if not admin_user["bofh"]:
        log.warning(f"Non-BOFH user {admin_user['user_id']} denied access to create attribute")
        return JSONResponse(
            content={"error": "Only BOFH can manage attributes"}, status_code=403
        )

    if not item.name:
        return JSONResponse(
            content={"error": "Attribute name is required"}, status_code=400
        )

    if not (
        attr := await attribute_add(
            name=item.name, description=item.description, example=item.example
        )
    ):
        return JSONResponse(
            content={"error": "Attribute already exists"}, status_code=409
        )

    return JSONResponse(content={"result": attr})


@router.delete("/admin/attributes/{attribute_id}", include_in_schema=False)
async def delete_attribute(
    request: Request,
    attribute_id: int,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Delete an onboarding attribute. BOFH only.

    Parameters:
        request (Request): The incoming HTTP request.
        attribute_id (int): The ID of the attribute to delete.
        admin_user (dict): The current user.

    Returns:
        JSONResponse: The result of the operation.
    """

    if not admin_user["bofh"]:
        log.warning(f"Non-BOFH user {admin_user['user_id']} denied access to delete attribute {attribute_id}")
        return JSONResponse(
            content={"error": "Only BOFH can manage attributes"}, status_code=403
        )

    if not await attribute_delete(attribute_id):
        return JSONResponse(content={"error": "Attribute not found"}, status_code=404)

    return JSONResponse(content={"result": {"status": "OK"}})
