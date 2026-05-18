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

from pydantic import BaseModel
from typing import Literal, Optional


class TranscriptionStatusPut(BaseModel):
    language: Optional[str] = None
    speakers: Optional[int] = 0
    output_format: Optional[str] = None
    encryption_password: Optional[str] = None


class TranscriptionResultPut(BaseModel):
    format: Optional[str] = None
    data: Optional[str] = None


class ModifyUserRequest(BaseModel):
    active: Optional[bool] = None
    admin: Optional[bool] = None
    admin_domains: Optional[str] = None
    reset_manual: Optional[bool] = None


class CreateGroupRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    quota_seconds: Optional[int] = 0


class UpdateGroupRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    usernames: Optional[list] = []
    quota_seconds: Optional[int] = 0
    quota: Optional[int] = 0


class CreateCustomerRequest(BaseModel):
    customer_abbr: Optional[str] = None
    partner_id: str
    name: str
    priceplan: Optional[str] = "variable"
    base_fee: Optional[float] = 0
    realms: Optional[str] = ""
    contact_email: Optional[str] = ""
    support_contact_email: Optional[str] = ""
    notes: Optional[str] = ""
    blocks_purchased: Optional[int] = 0


class UpdateCustomerRequest(BaseModel):
    customer_abbr: Optional[str] = None
    partner_id: Optional[str] = None
    name: Optional[str] = None
    priceplan: Optional[str] = None
    base_fee: Optional[float] = None
    realms: Optional[str] = None
    contact_email: Optional[str] = None
    support_contact_email: Optional[str] = None
    notes: Optional[str] = None
    blocks_purchased: Optional[int] = None


class TranscribeExternalPost(BaseModel):
    language: Optional[str]
    model: Optional[str]
    output_format: Optional[str]
    user_id: Optional[str]
    file_url: Optional[str]
    id: Optional[str]
    service_id: Optional[str]


class VideoStreamRequestBody(BaseModel):
    encryption_password: Optional[str] = ""


class CreateAttributeRuleRequest(BaseModel):
    name: str
    attribute_name: str
    attribute_condition: str
    attribute_value: str
    realm: Optional[str] = None
    activate: bool = False
    admin: bool = False
    deny: bool = False
    assign_to_group: Optional[str] = None
    notify_job: bool = False
    notify_deletion: bool = False
    owner_domains: Optional[str] = None
    enabled: bool = True


class UpdateAttributeRuleRequest(BaseModel):
    name: Optional[str] = None
    attribute_name: Optional[str] = None
    attribute_condition: Optional[str] = None
    attribute_value: Optional[str] = None
    realm: Optional[str] = None
    activate: Optional[bool] = None
    admin: Optional[bool] = None
    deny: Optional[bool] = None
    assign_to_group: Optional[str] = None
    notify_job: Optional[bool] = None
    notify_deletion: Optional[bool] = None
    owner_domains: Optional[str] = None
    enabled: Optional[bool] = None


class CreateOnboardingAttributeRequest(BaseModel):
    name: str
    description: str = ""
    example: str = ""


class TestRulesRequest(BaseModel):
    rule_ids: list[int]


class NotificationSettings(BaseModel):
    notify_on_job: Optional[bool] = None
    notify_on_deletion: Optional[bool] = None
    notify_on_user: Optional[bool] = None
    notify_on_quota: Optional[bool] = None
    notify_on_weekly_report: Optional[bool] = None


class UserUpdateRequest(BaseModel):
    email: Optional[str] = None
    encryption_password: Optional[str] = None
    encryption: Optional[bool] = False
    notifications: Optional[NotificationSettings] = None
    reset_password: Optional[bool] = False
    verify_password: Optional[bool] = False
    dark_mode: Optional[Literal["dark", "light", "auto"]] = None


class TranscriptionJobUpdateRequest(BaseModel):
    status: Optional[str] = None
    error: Optional[str] = None
    transcribed_seconds: Optional[float] = None


class TranscriptionResultRequest(BaseModel):
    format: str = ""
    result: str | dict


class CreateAnnouncementRequest(BaseModel):
    message: str
    severity: Optional[str] = "info"
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    enabled: bool = True


class UpdateAnnouncementRequest(BaseModel):
    message: Optional[str] = None
    severity: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    enabled: Optional[bool] = None
