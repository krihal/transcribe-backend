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

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import Column, Index
from sqlalchemy.types import Enum as SQLAlchemyEnum
from sqlmodel import Field, Relationship, SQLModel

#
#                              +---------------------------+
#                              |           Model           |
#                              |---------------------------|
#                              | id (PK)                   |
#                              | name (unique)             |
#                              | description               |
#                              | active (bool)             |
#                              +-------------+-------------+
#                                            ^
#                                            |
#                              +-------------+-------------+
#                              |      GroupModelLink       |
#                              |---------------------------|
#                              | group_id (FK->Group.id)   |
#                              | model_id (FK->Model.id)   |
#                              +-------------+-------------+
#                                            ^
#                                            |
# +--------------------------+    +----------+-----------+    +-----------------------------+
# |          Group           |    |    GroupUserLink     |    |            User             |
# |--------------------------|    |----------------------|    |-----------------------------|
# | id (PK)                  |<-->| group_id (FK)        |<-->| id (PK)                     |
# | name                     |    | user_id (FK)         |    | user_id (unique str)        |
# | realm                    |    | role                 |    | username                    |
# | description              |    | in_group (bool)      |    | realm                       |
# | created_at               |    +----------------------+    | email                       |
# | owner_user_id (->User)   |                                | admin (bool)                |
# | quota_seconds            |                                | admin_domains               |
# +------------+-------------+                                | bofh (bool)                 |
#              ^                                              | active (bool)               |
#              | assign_to_group                              | deleted (bool)              |
#              |                                              | manually_activated          |
# +------------+-------------+                                | manually_deactivated        |
# |      AttributeRule       |                                | manually_set_notifications  |
# |--------------------------|                                | notifications               |
# | id (PK)                  |                                | transcribed_seconds         |
# | name                     |                                | last_login                  |
# | attribute_name           |                                | encryption_settings         |
# | attribute_condition      |                                | private_key / public_key    |
# | attribute_value          |                                | dark_mode (enum)            |
# | enabled (bool)           |                                +--------------+--------------+
# | activate / admin / deny  |                                               ^
# | notify_job               |                  +----------------------------+
# | notify_deletion          |                  |
# | assign_to_group (->Grp)  |                  |
# | realm / owner_domains    |                  |
# +--------------------------+      +-----------+--------------+    +--------------------------+
#                                   |           Job            |    |    NotificationsSent     |
#                                   |--------------------------|    |--------------------------|
#                                   | id (PK)                  |    | id (PK)                  |
#                                   | uuid (UUID, unique)      |    | user_id (->User)         |
#                                   | user_id (->User)         |    | notification_type        |
#                                   | external_id              |    | uuid (e.g. Job.uuid)     |
#                                   | external_user_id         |    | sent_at                  |
#                                   | client_dn                |    +--------------------------+
#                                   | status (enum)            |
#                                   | job_type (enum)          |
#                                   | output_format (enum)     |
#                                   | language / model_type    |
#                                   | speakers                 |
#                                   | created_at / updated_at  |
#                                   | deletion_date            |
#                                   | filename / error         |
#                                   | transcribed_seconds      |
#                                   +-----------+--------------+
#                                               ^
#                                               | job_id = Job.uuid
#                                               |
#                                   +-----------+--------------+
#                                   |        JobResult         |
#                                   |--------------------------|
#                                   | id (PK)                  |
#                                   | job_id (->Job.uuid)      |
#                                   | user_id (->User)         |
#                                   | result (JSON)            |
#                                   | result_srt               |
#                                   | external_id              |
#                                   | created_at               |
#                                   +--------------------------+
#
# Standalone tables (no enforced FK):
#
# +--------------------------+  +--------------------------+  +--------------------------+
# |        Customer          |  |       Announcement       |  |        PageView          |
# |--------------------------|  |--------------------------|  |--------------------------|
# | id (PK)                  |  | id (PK)                  |  | id (PK)                  |
# | customer_abbr (unique)   |  | message                  |  | path                     |
# | partner_id               |  | severity (enum)          |  | timestamp                |
# | name                     |  | starts_at / ends_at      |  +--------------------------+
# | contact_email            |  | enabled                  |
# | support_contact_email    |  | created_at / created_by  |  +--------------------------+
# | priceplan (enum)         |  +--------------------------+  |      WorkerHealth        |
# | base_fee                 |                                |--------------------------|
# | blocks_purchased         |  +--------------------------+  | id (PK)                  |
# | realms (CSV -> User)     |  |   OnboardingAttribute    |  | worker_id                |
# | notes / created_at       |  |--------------------------|  | load_avg / memory_usage  |
# +--------------------------+  | id (PK)                  |  | gpu_usage (JSON)         |
#                               | name (unique)            |  | created_at               |
#                               | description / example    |  +--------------------------+
#                               +--------------------------+


class JobStatusEnum(str, Enum):
    """
    Enum representing the status of a job.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"


class JobStatus(BaseModel):
    """
    Model representing the status of a job.
    """

    status: JobStatusEnum
    error: Optional[str] = None


class OutputFormatEnum(str, Enum):
    """
    Enum representing the output format of the transcription.
    """

    TXT = "txt"
    SRT = "srt"
    CSV = "csv"
    NONE = "none"


class PricePlanEnum(str, Enum):
    """
    Enum representing the pricing plan type.
    """

    FIXED = "fixed"
    VARIABLE = "variable"


class JobType(str, Enum):
    """
    Enum representing the type of job.
    """

    TRANSCRIPTION = "transcription"


class JobResult(SQLModel, table=True):
    """
    Model representing the result of a job.
    """

    __tablename__ = "job_results"
    __table_args__ = (
        Index("ix_job_results_job_id_user_id", "job_id", "user_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True, description="Primary key")
    job_id: str = Field(
        index=True,
        unique=True,
        description="UUID of the job",
    )
    user_id: str = Field(
        index=True,
        description="User ID associated with the job",
    )
    result: Optional[str] = Field(
        default=None,
        description="JSON formatted transcription result",
    )
    result_srt: Optional[str] = Field(
        default=None,
        description="SRT formatted transcription result",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="Creation timestamp",
    )
    external_id: str = Field(
        index=True,
        unique=True,
        description="UUID of the job",
        default=None,
        nullable=True,
    )

    def as_dict(self) -> dict:
        """
        Convert the job result object to a dictionary.
        Returns:
            dict: The job result object as a dictionary.
        """
        return {
            "id": self.id,
            "job_id": self.job_id,
            "user_id": self.user_id,
            "result": self.result,
            "result_srt": self.result_srt,
            "external_id": self.external_id,
        }


class Job(SQLModel, table=True):
    """
    Model representing a job in the system.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_user_id_job_type", "user_id", "job_type"),
        Index("ix_jobs_status_deletion_date", "status", "deletion_date"),
        Index("ix_jobs_user_id_created_at", "user_id", "created_at"),
        Index("ix_jobs_status_created_at", "status", "created_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True, description="Primary key")
    uuid: str = Field(
        default_factory=lambda: str(uuid4()),
        index=True,
        unique=True,
        description="UUID of the job",
    )
    user_id: Optional[str] = Field(
        default=None,
        index=True,
        description="User ID associated with the job",
    )
    external_id: Optional[str] = Field(
        default=None,
        index=True,
        description="ID used to refer to this job by external software",
    )

    external_user_id: Optional[str] = Field(
        default=None,
        index=True,
        description="ID of the user in the external system requesting this job",
    )

    client_dn: Optional[str] = Field(
        default=None,
        index=True,
        description="Client_dn associated with this job",
    )
    status: JobStatusEnum = Field(
        default=None,
        sa_column=Field(sa_column=SQLAlchemyEnum(JobStatusEnum)),
        description="Current status of the job",
    )
    job_type: JobType = Field(
        default=None,
        sa_column=Field(sa_column=SQLAlchemyEnum(JobType)),
        description="Type of the job",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="Creation timestamp",
    )
    updated_at: datetime = Field(
        sa_column_kwargs={"onupdate": lambda: datetime.now(UTC).replace(tzinfo=None)},
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="Last updated timestamp",
    )
    deletion_date: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
        description="Date when the job will be deleted",
    )
    language: str = Field(default="Swedish", description="Language used for the job")
    model_type: str = Field(default="base", description="Model type used for the job")
    speakers: Optional[str] = Field(
        default=None, description="Number of speakers in the audio"
    )
    error: Optional[str] = Field(default=None, description="Error message if any")
    filename: str = Field(default="", description="Filename of the audio file")
    output_format: OutputFormatEnum = Field(
        default=OutputFormatEnum.TXT,
        sa_column=Field(sa_column=SQLAlchemyEnum(OutputFormatEnum)),
        description="Output format of the transcription",
    )
    transcribed_seconds: int = Field(default=0, description="Transcribed seconds")

    def as_dict(self) -> dict:
        """
        Convert the job object to a dictionary.
        Returns:
            dict: The job object as a dictionary.
        """

        return {
            "id": self.id,
            "uuid": self.uuid,
            "user_id": self.user_id,
            "external_id": self.external_id,
            "external_user_id": self.external_user_id,
            "status": self.status,
            "job_type": self.job_type,
            "created_at": str(self.created_at),
            "updated_at": str(self.updated_at),
            "deletion_date": str(self.deletion_date),
            "language": self.language,
            "model_type": self.model_type,
            "filename": self.filename,
            "speakers": self.speakers,
            "output_format": self.output_format,
            "error": self.error,
            "transcribed_seconds": self.transcribed_seconds,
        }


class Jobs(BaseModel):
    """
    Model representing a list of jobs.
    """

    jobs: List[Job]


class GroupUserLink(SQLModel, table=True):
    """
    Link table between groups and users.
    Defines which users belong to which groups.
    """

    __tablename__ = "group_user_link"
    __table_args__ = (
        Index("ix_group_user_link_group_id_user_id", "group_id", "user_id"),
        Index("ix_group_user_link_user_id_group_id", "user_id", "group_id"),
    )

    group_id: Optional[int] = Field(
        default=None, foreign_key="groups.id", primary_key=True
    )
    user_id: Optional[int] = Field(
        default=None, foreign_key="users.id", primary_key=True
    )
    role: str = Field(default="member", description="Role of the user in the group")
    in_group: bool = Field(
        default=True, description="Indicates if the user is currently in the group"
    )


class DarkModeEnum(str, Enum):
    """
    Enum representing the user's theme preference.
    """

    DARK = "dark"
    LIGHT = "light"
    AUTO = "auto"


class User(SQLModel, table=True):
    """
    Model representing a user in the system.
    """

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True, description="Primary key")
    user_id: str = Field(
        default=None,
        index=True,
        description="User ID",
    )
    username: str = Field(
        default=None,
        index=True,
        description="Username of the user",
    )
    realm: str = Field(
        default=None,
        index=True,
        description="User realm",
    )
    admin: bool = Field(
        default=False,
        description="Indicates if the user is an admin",
    )
    admin_domains: Optional[str] = Field(
        default=None,
        description="Comma-separated list of domains the admin manages",
    )
    bofh: bool = Field(
        default=False,
        description="Indicates if the user is a BOFH",
    )
    transcribed_seconds: int = Field(
        default=None,
        description="Transcribed seconds",
    )
    last_login: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="Last login timestamp",
    )
    active: bool = Field(
        default=False,
        description="Indicates if the user is active",
    )
    groups: List["Group"] = Relationship(
        back_populates="users", link_model=GroupUserLink
    )
    encryption_settings: Optional[bool] = Field(
        default=False,
        description="Indicates if the user has encryption settings enabled",
    )
    private_key: Optional[str] = Field(
        default=None,
        description="User's private key for encryption, password protected",
    )
    public_key: Optional[str] = Field(
        default=None,
        description="User's public key for encryption",
    )
    email: Optional[str] = Field(
        default=None,
        description="User's email address",
    )
    notifications: Optional[str] = Field(
        default=None,
        description="User's notification preferences",
    )
    deleted: bool = Field(
        default=False,
        description="Indicates if the user has been soft-deleted",
    )
    manually_deactivated: bool = Field(
        default=False,
        description="Indicates if the user was manually deactivated by an admin",
    )
    manually_activated: bool = Field(
        default=False,
        description="Indicates if the user was manually activated by an admin, preventing rules from deactivating",
    )
    manually_set_notifications: bool = Field(
        default=False,
        description="Indicates if the user manually changed their notification preferences, preventing rules from re-applying notification settings",
    )
    dark_mode: DarkModeEnum = Field(
        default=DarkModeEnum.AUTO,
        sa_column=Column(
            "dark_mode",
            SQLAlchemyEnum(
                DarkModeEnum,
                name="darkmodeenum",
                values_callable=lambda x: [e.value for e in x],
                create_type=False,
            ),
            nullable=False,
            server_default="auto",
        ),
        description="User's theme preference: dark, light, or auto",
    )

    def as_dict(self) -> dict:
        """
        Convert the user object to a dictionary.
        Returns:
            dict: The user object as a dictionary.
        """

        return {
            "id": self.id,
            "active": self.active,
            "admin": self.admin,
            "admin_domains": self.admin_domains,
            "bofh": self.bofh,
            "email": self.email,
            "encryption_settings": self.encryption_settings,
            "last_login": str(self.last_login),
            "deleted": self.deleted,
            "manually_activated": self.manually_activated,
            "manually_deactivated": self.manually_deactivated,
            "manually_set_notifications": self.manually_set_notifications,
            "notifications": self.notifications,
            "private_key": self.private_key,
            "public_key": self.public_key,
            "realm": self.realm,
            "transcribed_seconds": self.transcribed_seconds,
            "user_id": self.user_id,
            "username": self.username,
            "dark_mode": self.dark_mode,
        }


class Users(BaseModel):
    """
    Model representing a list of users.
    """

    users: List[User]


# Block diagram of the connection between users, groups, quota, models, rules
# and billing.
#
# User <--> GroupUserLink <--> Group <--> GroupModelLink <--> Model
#   ^                            ^
#   | manual_* flags             | assign_to_group
#   | notifications              |
#   |                            |
#   +-------- AttributeRule -----+
#              (matches JWT/SAML claims, applies actions:
#               activate, admin, deny, assign_to_group,
#               notify_job, notify_deletion)
#
# Job.user_id          -> User.user_id
# JobResult.job_id     -> Job.uuid
# JobResult.user_id    -> User.user_id
# NotificationsSent    -> User.user_id (+ uuid of e.g. Job)
# Customer.realms      -> CSV loose link to User.realm / Group.realm
# OnboardingAttribute  -> reference list for AttributeRule.attribute_name
#
# -----------------------------------------------------------
# Design allows:
# - Users belong to multiple groups
# - Groups have access to multiple models
# - Each group has a monthly quota in seconds
# - Each user tracks total transcribed seconds
# - Admin users manage groups/users in their admin_domains
# - BOFH users view statistics across all realms
# - Each group has an owner or primary contact user
# - AttributeRule auto-provisions users at login from JWT/SAML
#   claims; manual_* flags on User block rule overwrite
# - Customer groups realms for billing (fixed or variable plan,
#   blocks_purchased for fixed plans)
# - Announcement drives system-wide banner with severity/window
# - WorkerHealth tracks GPU worker load / memory / GPU usage
# - PageView captures anonymous action analytics
# -----------------------------------------------------------


class GroupModelLink(SQLModel, table=True):
    """
    Link table between groups and models.
    Defines which models a group has access to.
    """

    __tablename__ = "group_model_link"
    __table_args__ = (
        Index("ix_group_model_link_group_id_model_id", "group_id", "model_id"),
    )

    group_id: int = Field(foreign_key="groups.id", primary_key=True)
    model_id: int = Field(foreign_key="models.id", primary_key=True)


class Model(SQLModel, table=True):
    """
    Model representing a transcription model type.
    """

    __tablename__ = "models"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(
        index=True, unique=True, description="Model name (e.g., base, large)"
    )
    description: str = Field(default=None, description="Model description")
    active: bool = Field(
        default=True, description="Whether the model is currently available"
    )

    groups: List["Group"] = Relationship(
        back_populates="allowed_models", link_model=GroupModelLink
    )


class Group(SQLModel, table=True):
    """
    Model representing a user group.
    """

    __tablename__ = "groups"

    id: Optional[int] = Field(default=None, primary_key=True, unique=True)
    name: str = Field(index=True, unique=False)
    realm: str = Field(index=True, description="Realm the group belongs to")
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Group management
    owner_user_id: Optional[str] = Field(
        description="Owner or primary contact for this group"
    )
    quota_seconds: Optional[int] = Field(
        default=None, description="Monthly quota in seconds"
    )

    # Relationships
    users: List["User"] = Relationship(
        back_populates="groups", link_model=GroupUserLink
    )
    allowed_models: List["Model"] = Relationship(
        back_populates="groups", link_model=GroupModelLink
    )

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "realm": self.realm,
            "description": self.description,
            "created_at": str(self.created_at),
            "owner_user_id": self.owner_user_id,
            "quota_seconds": self.quota_seconds if self.quota_seconds else 0,
            "user_count": len(self.users),
            "transcribed_seconds_total": sum(
                u.transcribed_seconds or 0 for u in self.users
            ),
            "allowed_models": [m.name for m in self.allowed_models],
            "users": [u.as_dict() for u in self.users] if self.users else [],
        }


class Customer(SQLModel, table=True):
    """
    Model representing a customer organization.
    Note: Customers are linked to users via the 'realms' field, not via foreign key.
    """

    __tablename__ = "customer"

    id: Optional[int] = Field(default=None, primary_key=True, description="Primary key")
    customer_abbr: str = Field(
        default=None,
        index=True,
        unique=True,
        description="Unique customer identifier",
    )
    partner_id: str = Field(
        default=None,
        index=True,
        unique=False,
        description="Partner ID associated with the customer",
    )
    name: str = Field(
        default=None,
        index=True,
        description="Customer organization name",
    )
    contact_email: Optional[str] = Field(
        default=None,
        description="Contact email for the customer organization",
    )
    support_contact_email: Optional[str] = Field(
        default=None,
        description="Support contact email shown to end users in the help dialog",
    )
    priceplan: PricePlanEnum = Field(
        default=PricePlanEnum.VARIABLE,
        sa_column=Field(sa_column=SQLAlchemyEnum(PricePlanEnum)),
        description="Pricing plan type (fixed or variable)",
    )
    base_fee: Optional[int] = Field(
        default=0,
        description="Base monthly fee for the customer",
    )
    realms: str = Field(
        default="",
        description="Comma-separated list of realms associated with this customer",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes about the customer",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="Creation timestamp",
    )
    blocks_purchased: Optional[int] = Field(
        default=0,
        description="Number of 4000-minute blocks purchased (for fixed plan)",
    )

    def as_dict(self) -> dict:
        """
        Convert the customer object to a dictionary.
        Returns:
            dict: The customer object as a dictionary.
        """

        return {
            "id": self.id,
            "customer_abbr": self.customer_abbr,
            "partner_id": self.partner_id,
            "name": self.name,
            "contact_email": self.contact_email,
            "support_contact_email": self.support_contact_email,
            "priceplan": self.priceplan,
            "base_fee": self.base_fee if self.base_fee else 0,
            "realms": self.realms,
            "notes": self.notes,
            "created_at": str(self.created_at),
            "blocks_purchased": self.blocks_purchased if self.blocks_purchased else 0,
        }


class NotificationsSent(SQLModel, table=True):
    """
    Model representing notifications sent to users.
    """

    __tablename__ = "notifications_sent"
    __table_args__ = (
        Index("ix_notifications_sent_user_id_uuid_type", "user_id", "uuid", "notification_type"),
    )

    id: Optional[int] = Field(default=None, primary_key=True, description="Primary key")
    user_id: str = Field(
        default=None,
        index=True,
        description="User ID who received the notification",
    )
    notification_type: str = Field(
        default=None,
        description="Type of notification sent",
    )
    sent_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="Timestamp when the notification was sent",
    )
    uuid: str = Field(
        default=None,
        index=True,
        description="UUID of for example a job we've sent notification about",
    )

    def as_dict(self) -> dict:
        """
        Convert the notification object to a dictionary.
        Returns:
            dict: The notification object as a dictionary.
        """

        return {
            "id": self.id,
            "user_id": self.user_id,
            "notification_type": self.notification_type,
            "sent_at": str(self.sent_at),
            "uuid": self.uuid,
        }


class PageView(SQLModel, table=True):
    """
    Model representing anonymous page view events for analytics.
    """

    __tablename__ = "page_views"
    __table_args__ = (
        Index("ix_page_views_timestamp_path", "timestamp", "path"),
        Index("ix_page_views_path_timestamp", "path", "timestamp"),
    )

    id: Optional[int] = Field(default=None, primary_key=True, description="Primary key")
    path: str = Field(index=True, description="Page path that was visited")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        index=True,
        description="Timestamp of the page view",
    )


class AttributeConditionEnum(str, Enum):
    """
    Enum representing the condition type for attribute matching.
    """

    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    CONTAINS = "CONTAINS"
    NOT_CONTAINS = "NOT_CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    REGEX_MATCH = "REGEX_MATCH"


class AttributeRule(SQLModel, table=True):
    """
    Model representing an attribute-based rule for automatic
    group assignment and user provisioning.
    """

    __tablename__ = "attribute_rules"

    id: Optional[int] = Field(default=None, primary_key=True, description="Primary key")
    name: str = Field(index=True, description="Human-readable rule name")
    attribute_name: str = Field(
        index=True, description="JWT claim / SAML friendly name to match"
    )
    attribute_condition: AttributeConditionEnum = Field(
        sa_column=Field(sa_column=SQLAlchemyEnum(AttributeConditionEnum)),
        description="Condition used to evaluate the attribute value",
    )
    attribute_value: str = Field(description="Value to compare against")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), description="Creation timestamp"
    )
    enabled: bool = Field(
        default=True, description="Whether this rule is currently active"
    )

    # Actions when rule matches
    activate: bool = Field(
        default=False,
        description="Automatically activate matching users",
    )
    admin: bool = Field(
        default=False,
        description="Grant admin privileges to matching users",
    )
    deny: bool = Field(
        default=False,
        description="Deny access to matching users",
    )
    assign_to_group: Optional[str] = Field(
        default=None,
        description="Group ID to assign matching users to",
    )
    notify_job: bool = Field(
        default=False,
        description="Enable transcription completed notifications for matching users",
    )
    notify_deletion: bool = Field(
        default=False,
        description="Enable upcoming file deletion notifications for matching users",
    )
    # Scope
    realm: Optional[str] = Field(
        default=None, index=True, description="Realm this rule applies to"
    )
    owner_domains: Optional[str] = Field(
        default=None,
        description="Comma-separated domains whose admins can manage this rule",
    )

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "attribute_name": self.attribute_name,
            "attribute_condition": self.attribute_condition.value
            if self.attribute_condition
            else None,
            "attribute_value": self.attribute_value,
            "created_at": str(self.created_at),
            "enabled": self.enabled,
            "activate": self.activate,
            "admin": self.admin,
            "deny": self.deny,
            "assign_to_group": self.assign_to_group,
            "notify_job": self.notify_job,
            "notify_deletion": self.notify_deletion,
            "realm": self.realm,
            "owner_domains": self.owner_domains,
        }


class OnboardingAttribute(SQLModel, table=True):
    """
    Model representing a supported SAML/JWT attribute that can be used
    when configuring attribute rules.
    """

    __tablename__ = "onboarding_attributes"

    id: Optional[int] = Field(default=None, primary_key=True, description="Primary key")
    name: str = Field(
        index=True, unique=True, description="Attribute friendly name"
    )
    description: str = Field(default="", description="Human-readable description")
    example: str = Field(default="", description="Example value")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "example": self.example,
        }


class AnnouncementSeverityEnum(str, Enum):
    """
    Enum representing the severity level of an announcement.
    """

    INFO = "info"
    MAINTENANCE = "maintenance"
    MAJOR_INCIDENT = "major_incident"


class Announcement(SQLModel, table=True):
    """
    Model representing a system-wide announcement banner.
    All times are in server-local time.
    """

    __tablename__ = "announcements"

    id: Optional[int] = Field(default=None, primary_key=True, description="Primary key")
    message: str = Field(description="Announcement message (may contain HTML links)")
    severity: AnnouncementSeverityEnum = Field(
        default=AnnouncementSeverityEnum.INFO,
        sa_column=Field(sa_column=SQLAlchemyEnum(AnnouncementSeverityEnum)),
        description="Severity level: info, maintenance, or major_incident",
    )
    starts_at: Optional[datetime] = Field(
        default=None,
        description="When the announcement becomes visible (server time, NULL = immediate)",
    )
    ends_at: Optional[datetime] = Field(
        default=None,
        description="When the announcement stops being visible (server time, NULL = no end)",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this announcement is currently active",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="Creation timestamp",
    )
    created_by: Optional[str] = Field(
        default=None,
        description="Username of the admin who created this announcement",
    )

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "message": self.message,
            "severity": self.severity.value if hasattr(self.severity, "value") else (self.severity or "info"),
            "starts_at": str(self.starts_at) if self.starts_at else None,
            "ends_at": str(self.ends_at) if self.ends_at else None,
            "enabled": self.enabled,
            "created_at": str(self.created_at),
            "created_by": self.created_by,
        }


class WebAuthnCredential(SQLModel, table=True):
    """
    Stores FIDO2/WebAuthn credentials for passkey-based encryption key derivation.
    The PRF extension output from these credentials is used as the encryption passphrase.
    """

    __tablename__ = "webauthn_credentials"
    __table_args__ = (
        Index("ix_webauthn_credentials_user_id", "user_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, description="User ID (matches users.user_id)")
    credential_id: str = Field(index=True, unique=True, description="Base64url-encoded credential ID")
    public_key: str = Field(description="COSE public key, base64url-encoded")
    sign_count: int = Field(default=0, description="Signature counter for replay protection")
    name: Optional[str] = Field(default=None, description="User-assigned label for this key")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="Registration timestamp",
    )

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "credential_id": self.credential_id,
            "name": self.name,
            "created_at": str(self.created_at),
        }


class WorkerHealth(SQLModel, table=True):
    __tablename__ = "worker_health"
    __table_args__ = (
        Index("ix_worker_health_worker_id", "worker_id"),
        Index("ix_worker_health_worker_id_created_at", "worker_id", "created_at"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    worker_id: str = Field(description="Identifier of the GPU worker")
    load_avg: float = Field(default=0, description="Load average")
    memory_usage: float = Field(default=0, description="Memory usage")
    gpu_usage: Optional[str] = Field(default=None, description="GPU usage as JSON")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="Timestamp when the health entry was recorded",
    )
