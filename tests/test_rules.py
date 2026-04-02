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

"""
Regression tests for attribute rules and manual override logic.

Uses an in-memory SQLite database to test evaluate_rules() and
apply_rule_actions() without requiring an external database.
"""

import os
import pytest
import pytest_asyncio

# Point to an in-memory SQLite database before importing any project modules
os.environ["API_DATABASE_URL"] = "sqlite://"

from contextlib import asynccontextmanager
from unittest.mock import patch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from db.models import AttributeConditionEnum, AttributeRule, Group, GroupUserLink, User
from db.attribute_rules import (
    _match_condition,
    _get_claim_values,
    evaluate_rules,
    apply_rule_actions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def db_session():
    """Create a fresh in-memory async SQLite database for each test."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()
    yield session
    await session.close()
    await engine.dispose()


@pytest_asyncio.fixture()
async def _patch_session(db_session):
    """Patch get_async_session everywhere to use the test database session."""

    @asynccontextmanager
    async def _get_async_session():
        try:
            yield db_session
            await db_session.flush()
        except Exception:
            await db_session.rollback()
            raise

    with (
        patch("db.attribute_rules.get_async_session", _get_async_session),
        patch("db.group.get_async_session", _get_async_session),
    ):
        yield db_session


async def _make_user(session, *, username="student@example.com", realm="example.com",
                     user_id="uid-1", active=False, manually_deactivated=False,
                     manually_activated=False) -> User:
    """Helper to create and persist a User."""
    user = User(
        username=username,
        realm=realm,
        user_id=user_id,
        active=active,
        manually_deactivated=manually_deactivated,
        manually_activated=manually_activated,
        transcribed_seconds=0,
    )
    session.add(user)
    await session.flush()
    return user


async def _make_rule(session, *, name="test-rule", attribute_name="affiliation",
                     condition=AttributeConditionEnum.EQUALS, attribute_value="student",
                     realm=None, activate=False, admin=False, deny=False,
                     assign_to_group=None, enabled=True) -> AttributeRule:
    """Helper to create and persist an AttributeRule."""
    rule = AttributeRule(
        name=name,
        attribute_name=attribute_name,
        attribute_condition=condition,
        attribute_value=attribute_value,
        realm=realm,
        activate=activate,
        admin=admin,
        deny=deny,
        assign_to_group=assign_to_group,
        enabled=enabled,
    )
    session.add(rule)
    await session.flush()
    return rule


# ---------------------------------------------------------------------------
# Unit tests for _match_condition
# ---------------------------------------------------------------------------

class TestMatchCondition:
    def test_equals(self):
        assert _match_condition(AttributeConditionEnum.EQUALS, "student", "student")
        assert not _match_condition(AttributeConditionEnum.EQUALS, "staff", "student")

    def test_not_equals(self):
        assert _match_condition(AttributeConditionEnum.NOT_EQUALS, "staff", "student")
        assert not _match_condition(AttributeConditionEnum.NOT_EQUALS, "student", "student")

    def test_contains(self):
        assert _match_condition(AttributeConditionEnum.CONTAINS, "student@uni.se", "student")
        assert not _match_condition(AttributeConditionEnum.CONTAINS, "staff@uni.se", "student")

    def test_not_contains(self):
        assert _match_condition(AttributeConditionEnum.NOT_CONTAINS, "staff@uni.se", "student")
        assert not _match_condition(AttributeConditionEnum.NOT_CONTAINS, "student@uni.se", "student")

    def test_starts_with(self):
        assert _match_condition(AttributeConditionEnum.STARTS_WITH, "student@uni.se", "student")
        assert not _match_condition(AttributeConditionEnum.STARTS_WITH, "a-student", "student")

    def test_ends_with(self):
        assert _match_condition(AttributeConditionEnum.ENDS_WITH, "a-student", "student")
        assert not _match_condition(AttributeConditionEnum.ENDS_WITH, "student@uni.se", "student")

    def test_regex_match(self):
        assert _match_condition(AttributeConditionEnum.REGEX_MATCH, "student123", r"student\d+")
        assert not _match_condition(AttributeConditionEnum.REGEX_MATCH, "staff123", r"^student\d+$")

    def test_regex_invalid_pattern(self):
        assert not _match_condition(AttributeConditionEnum.REGEX_MATCH, "test", r"[invalid")


# ---------------------------------------------------------------------------
# Unit tests for _get_claim_values
# ---------------------------------------------------------------------------

class TestGetClaimValues:
    def test_single_value(self):
        assert _get_claim_values({"role": "student"}, "role") == ["student"]

    def test_list_value(self):
        assert _get_claim_values({"roles": ["student", "member"]}, "roles") == ["student", "member"]

    def test_missing_claim(self):
        assert _get_claim_values({}, "role") == []

    def test_numeric_value(self):
        assert _get_claim_values({"level": 5}, "level") == ["5"]


# ---------------------------------------------------------------------------
# Tests for evaluate_rules
# ---------------------------------------------------------------------------

class TestEvaluateRules:
    @pytest.mark.asyncio
    async def test_deny_rule_matches(self, _patch_session):
        session = _patch_session
        user = await _make_user(session, active=True)
        await _make_rule(session, deny=True)

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions["deny"] is True

    @pytest.mark.asyncio
    async def test_activate_rule_matches(self, _patch_session):
        session = _patch_session
        user = await _make_user(session, active=False)
        await _make_rule(session, activate=True)

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions["activate"] is True

    @pytest.mark.asyncio
    async def test_admin_rule_matches(self, _patch_session):
        session = _patch_session
        user = await _make_user(session, active=True)
        await _make_rule(session, admin=True)

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions["admin"] is True

    @pytest.mark.asyncio
    async def test_no_match_returns_default_actions(self, _patch_session):
        session = _patch_session
        user = await _make_user(session, active=True)
        await _make_rule(session, deny=True, attribute_value="staff")

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions["deny"] is False
        assert actions["activate"] is False

    @pytest.mark.asyncio
    async def test_disabled_rule_is_skipped(self, _patch_session):
        session = _patch_session
        user = await _make_user(session, active=True)
        await _make_rule(session, deny=True, enabled=False)

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions["deny"] is False

    @pytest.mark.asyncio
    async def test_realm_scoping(self, _patch_session):
        session = _patch_session
        user = await _make_user(session, realm="example.com")
        await _make_rule(session, deny=True, realm="other.com")

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions["deny"] is False

    @pytest.mark.asyncio
    async def test_realm_scoping_matches(self, _patch_session):
        session = _patch_session
        user = await _make_user(session, realm="example.com")
        await _make_rule(session, deny=True, realm="example.com")

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions["deny"] is True


# ---------------------------------------------------------------------------
# Tests for manual override
# ---------------------------------------------------------------------------

class TestManualOverride:
    @pytest.mark.asyncio
    async def test_manually_deactivated_skips_all_rules(self, _patch_session):
        """A manually deactivated user should not be affected by any rules."""
        session = _patch_session
        user = await _make_user(session, active=False, manually_deactivated=True)
        await _make_rule(session, activate=True)

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions == {}

    @pytest.mark.asyncio
    async def test_manually_activated_ignores_deny(self, _patch_session):
        """A manually activated user should NOT be denied by rules."""
        session = _patch_session
        user = await _make_user(session, active=True, manually_activated=True)
        await _make_rule(session, deny=True)

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions["deny"] is False

    @pytest.mark.asyncio
    async def test_manually_activated_still_gets_admin(self, _patch_session):
        """A manually activated user should still get admin from rules."""
        session = _patch_session
        user = await _make_user(session, active=True, manually_activated=True)
        await _make_rule(session, admin=True)

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions["admin"] is True

    @pytest.mark.asyncio
    async def test_manually_activated_skips_group(self, _patch_session):
        """A manually activated user should NOT be auto-assigned to a group."""
        session = _patch_session
        user = await _make_user(session, active=True, manually_activated=True)
        await _make_rule(session, assign_to_group="42")

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions["group"] is None

    @pytest.mark.asyncio
    async def test_manually_activated_deny_and_group_combined(self, _patch_session):
        """With deny+group rules, manually activated user is neither denied nor auto-assigned."""
        session = _patch_session
        user = await _make_user(session, active=True, manually_activated=True)
        await _make_rule(session, name="deny-students", deny=True)
        await _make_rule(session, name="assign-group", assign_to_group="7",
                         attribute_name="affiliation", attribute_value="student")

        jwt = {"affiliation": "student", "preferred_username": "student@example.com"}
        actions = await evaluate_rules(jwt, user.as_dict())

        assert actions["deny"] is False
        assert actions["group"] is None


# ---------------------------------------------------------------------------
# Tests for apply_rule_actions
# ---------------------------------------------------------------------------

class TestApplyRuleActions:
    @pytest.mark.asyncio
    async def test_deny_deactivates_user(self, _patch_session):
        session = _patch_session
        user = await _make_user(session, active=True)

        await apply_rule_actions({"deny": True, "activate": False, "admin": False, "group": None}, user.as_dict())
        await session.refresh(user)

        assert user.active is False

    @pytest.mark.asyncio
    async def test_activate_enables_user(self, _patch_session):
        session = _patch_session
        user = await _make_user(session, active=False)

        await apply_rule_actions({"deny": False, "activate": True, "admin": False, "group": None}, user.as_dict())
        await session.refresh(user)

        assert user.active is True

    @pytest.mark.asyncio
    async def test_admin_grants_admin(self, _patch_session):
        session = _patch_session
        user = await _make_user(session, active=True)

        await apply_rule_actions({"deny": False, "activate": False, "admin": True, "group": None}, user.as_dict())
        await session.refresh(user)

        assert user.admin is True

    @pytest.mark.asyncio
    async def test_deny_takes_precedence_over_activate(self, _patch_session):
        """If both deny and activate are set, deny wins."""
        session = _patch_session
        user = await _make_user(session, active=True)

        await apply_rule_actions({"deny": True, "activate": True, "admin": False, "group": None}, user.as_dict())
        await session.refresh(user)

        assert user.active is False

    @pytest.mark.asyncio
    async def test_empty_actions_is_noop(self, _patch_session):
        session = _patch_session
        user = await _make_user(session, active=True)

        await apply_rule_actions({}, user.as_dict())
        await session.refresh(user)

        assert user.active is True


# ---------------------------------------------------------------------------
# Regression test: the original bug
# ---------------------------------------------------------------------------

class TestRegressionManualActivateVsDeny:
    @pytest.mark.asyncio
    async def test_manually_activated_student_survives_deny_rule(self, _patch_session):
        """
        Regression: An admin manually activates a student. A deny rule
        exists for students. The student logs in. The deny rule must NOT
        deactivate the student.
        """
        session = _patch_session
        user = await _make_user(session, active=True, manually_activated=True)
        await _make_rule(session, name="block-students", deny=True,
                         attribute_name="affiliation", attribute_value="student",
                         realm="example.com")

        jwt = {
            "affiliation": "student",
            "preferred_username": "student@example.com",
            "realm": "example.com",
        }

        actions = await evaluate_rules(jwt, user.as_dict())
        if actions:
            await apply_rule_actions(actions, user.as_dict())

        await session.refresh(user)
        assert user.active is True, (
            "Manually activated user was deactivated by deny rule"
        )
