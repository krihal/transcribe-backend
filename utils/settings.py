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

import os

from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Settings for the application.
    """

    @field_validator("OIDC_SCOPE", mode="before")
    @classmethod
    def decode_scope(cls, v: str) -> list[str]:
        return [str(x) for x in v.split(",")]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        validate_assignment=True,
        enable_decoding=False,
    )

    # API configuration.
    API_DATABASE_URL: str = "sqlite:///jobs.db"
    API_DEBUG: bool = True
    API_TITLE: str = "Sunet Scribe REST backend"
    API_DESCRIPTION: str = "A REST API for the Sunet Scribe service."
    API_FILE_STORAGE_DIR: str = ""
    API_PREFIX: str = "/api/v1"
    API_SECRET_KEY: str = ""
    API_VERSION: str = "1.1.0"
    API_WORKER_CLIENT_DN: str = "CN=TranscriberWorker,O=SUNET,ST=Stockholm,C=SE"
    API_KALTURA_CLIENT_DN: str = "CN=KalturaAdaptor,O=SUNET,ST=Stockholm,C=SE"
    API_CLIENT_VERIFICATION_ENABLED: bool = True
    API_CLIENT_VERIFICATION_HEADER: str = "x-client-legacy"
    API_PRIVATE_KEY_PASSWORD: str = ""

    # SMTP configuration.
    API_SMTP_HOST: str = ""
    API_SMTP_PORT: int = 25
    API_SMTP_USERNAME: str = ""
    API_SMTP_PASSWORD: str = ""
    API_SMTP_SENDER: str = ""
    API_SMTP_SSL: bool = False

    # Branding
    BRANDING_NAME: str = "Sunet Scribe"
    BRANDING_FRONTEND_URL: str = "https://scribe.sunet.se"
    BRANDING_ADMIN_URL: str = "https://scribe.sunet.se/admin"

    # OIDC configuration.
    OIDC_CLIENT_ID: str = ""
    OIDC_SCOPE: list[str] = []
    OIDC_CLIENT_SECRET: str = ""
    OIDC_METADATA_URL: str = ""
    OIDC_REDIRECT_URI: str = ""
    OIDC_REFRESH_URI: str = ""
    OIDC_FRONTEND_URI: str = ""

    # External job configuration.
    EXTERNAL_JOB_MODEL: str = "slower transcription (higher accuracy)"

    # Customer config
    CUSTOMER_MINUTES_PER_BLOCK: int = 4000

    # Crypto configuration.
    CRYPTO_KEY_SIZE: int = 4096
    CRYPTO_CHUNK_SIZE: int = (
        1024 * 1024
    )  # 1MB - must match chunk_size in encrypt_data_to_file

    # E-mail notifications
    NOTIFICATION_MAIL_UPDATED: dict = {
        "subject": "Your e-mail address have been updated",
        "message": """\
Hello,

Your e-mail address have been updated in {branding_name}.
If you did not perform this action, please contact support.

Best regards,
{branding_name}

This is an automated message from {branding_name}. If you need assistance, please contact your local support.
""",
    }

    NOTIFICATION_MAIL_TRANSCRIPTION_FINISHED: dict = {
        "subject": "Your transcription is ready in {branding_name}",
        "message": """\
Hello,

Your transcription job is now complete and ready to view in {branding_name}.
You can log in to the service to review, edit, or export your transcription:
{branding_frontend_url}

Best regards,
{branding_name}

This is an automated message from {branding_name}. If you need assistance, please contact your local support.
""",
    }

    NOTIFICATION_MAIL_TRANSCRIPTION_FAILED: dict = {
        "subject": "Your transcription job has failed",
        "message": """\
Hello,

Unfortunately, your transcription job could not be completed.

You can try submitting the job again via {branding_name}. In many cases, temporary issues are resolved automatically.

If the problem persists, please contact your local support.

No transcription data has been produced as a result of this job.

Best regards,
{branding_name}

This is an automated message from {branding_name}. If you need assistance, please contact your local support.
""",
    }

    NOTIFICATION_MAIL_TRANSCRIPTION_DELETED: dict = {
        "subject": "Your transcription job has been deleted",
        "message": """\
Hello,

One or more of your transcription jobs have been deleted from {branding_name} because they were older than 7 days.

{branding_name} automatically removes transcription jobs after 7 days for security and storage reasons.

The transcription and associated files are no longer available and cannot be recovered.

Best regards,
{branding_name}

This is an automated message from {branding_name}. If you need assistance, please contact your local support.
""",
    }

    NOTIFICATION_MAIL_TRANSCRIPTION_TO_BE_DELETED: dict = {
        "subject": "Your transcription job will be deleted soon",
        "message": """\
Hello,

One or more of your transcription jobs in {branding_name} are scheduled for deletion in 24 hours.

Transcription jobs are automatically removed after 7 days for security and storage reasons.

If you wish to keep the transcription, please log in to {branding_name} and export the transcription results before they are deleted.

After deletion, the transcription and associated files cannot be recovered.

Best regards,
{branding_name}

This is an automated message from {branding_name}. If you need assistance, please contact your local support.
""",
    }

    NOTIFICATION_MAIL_NEW_USER_CREATED: dict = {
        "subject": "A new user has been created",
        "message": """\
Hello,

A new user {username} has been created in {branding_name}.
The account is not yet active and requires approval by a local administrator before the user can access the service.

Please review and activate the new user via the {branding_name} administration interface:
{branding_admin_url}

No user data can been uploaded and no processing can take place until the account is activated.

Best regards,
{branding_name}

This is an automated message from {branding_name}. If you need assistance, please contact your local support.
""",
    }

    NOTIFICATION_MAIL_ACCOUNT_ACTIVATED: dict = {
        "subject": "Your {branding_name} account has been activated",
        "message": """\
Hello,

Your account in {branding_name} has now been activated by an administrator.

You can log in to the service and start using it at any time.

Please note that uploaded files and transcriptions are stored temporarily and are automatically removed after a limited retention period. Make sure to download any content you wish to keep.

Best regards,
{branding_name}

This is an automated message from {branding_name}. If you need assistance, please contact your local support.
""",
    }

    NOTIFICATION_MAIL_QUOTA_ALERT: dict = {
        "subject": "Block quota is nearing its limit",
        "message": """\
Hello,

The account quota for {customer_name} has reached {usage_percent}% utilization.

Usage summary:
- Blocks purchased: {blocks_purchased}
- Minutes included: {minutes_included}
- Minutes consumed: {minutes_consumed}
- Minutes remaining: {remaining_minutes}

Best regards,
{branding_name}

This is an automated message from {branding_name}. If you need assistance, please contact your local support.
""",
    }

    NOTIFICATION_MAIL_GROUP_QUOTA_ALERT: dict = {
        "subject": "Group is nearing its limit",
        "message": """\
Hello,

The group "{group_name}" has reached {usage_percent}% of its transcription limit.

Usage summary:
- Limit: {quota_minutes} minutes
- Used: {used_minutes} minutes
- Remaining: {remaining_minutes} minutes

Best regards,
{branding_name}

This is an automated message from {branding_name}. If you need assistance, please contact your local support.
""",
    }

    NOTIFICATION_MAIL_WEEKLY_USAGE_REPORT: dict = {
        "subject": "Weekly usage report for {branding_name}",
        "message": """\
Hello,

Here is the weekly usage report for {customer_name}:

Current month:
- Total users: {total_users}
- Files transcribed: {transcribed_files}
- Minutes transcribed: {transcribed_minutes}
- Minutes transcribed (external): {transcribed_minutes_external}

Block usage:
- Blocks purchased: {blocks_purchased}
- Blocks consumed: {blocks_consumed}
- Minutes included: {minutes_included}
- Minutes remaining: {remaining_minutes}
- Overage minutes: {overage_minutes}

Best regards,
{branding_name}

This is an automated message from {branding_name}. If you need assistance, please contact your local support.
""",
    }


@lru_cache
def get_settings() -> Settings:
    """
    Get the settings for the application.

    Returns:
        Settings: The application settings.
    """
    if not os.path.exists(Settings().API_FILE_STORAGE_DIR):
        os.makedirs(Settings().API_FILE_STORAGE_DIR)

    return Settings()
