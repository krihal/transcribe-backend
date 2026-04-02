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

import csv
import io

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from db.models import Customer, Job, JobType, User
from db.session import get_async_session, get_session
from typing import Optional
from utils.log import get_logger
from utils.notifications import notifications
from utils.settings import get_settings

settings = get_settings()
log = get_logger()


async def customer_create(
    customer_abbr: str,
    partner_id: str,
    name: str,
    priceplan: str,
    base_fee: int,
    realms: str,
    contact_email: Optional[str] = None,
    support_contact_email: Optional[str] = None,
    notes: Optional[str] = None,
    blocks_purchased: Optional[int] = 0,
) -> dict:
    """
    Create a new customer in the database.

    Parameters:
        customer_abbr (str): Abbreviation for the customer.
        partner_id (str): Partner ID associated with the customer.
        name (str): Full name of the customer.
        priceplan (str): Pricing plan for the customer (e.g., "fixed", "usage").
        base_fee (int): Base fee for the customer.
        realms (str): Comma-separated list of realms associated with the customer.
        contact_email (Optional[str]): Contact email for the customer.
        support_contact_email (Optional[str]): Support contact email shown to end users.
        notes (Optional[str]): Additional notes about the customer.
        blocks_purchased (Optional[int]): Number of blocks purchased (for fixed plans).

    Returns:
        dict: Dictionary representation of the created customer.
    """

    async with get_async_session() as session:
        customer = Customer(
            customer_abbr=customer_abbr,
            partner_id=partner_id,
            name=name,
            contact_email=contact_email,
            support_contact_email=support_contact_email,
            priceplan=priceplan,
            base_fee=base_fee,
            realms=realms,
            notes=notes,
            blocks_purchased=blocks_purchased if blocks_purchased else 0,
        )

        session.add(customer)
        await session.flush()

        log.info(f"Customer {customer.name} created with ID {customer.id}.")

        return customer.as_dict()


async def customer_get_from_user_id(user_id: str) -> Optional[dict]:
    """
    Get a customer by user_id.

    Parameters:
        user_id (str): The user ID to retrieve the associated customer.

    Returns:
        Optional[dict]: Dictionary representation of the customer if found, else empty dict.
    """

    async with get_async_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        if not (user := result.scalars().first()):
            return {}

        realm = user.realm

        result = await session.execute(
            select(Customer).where(Customer.realms.like(f"%{realm}%"))
        )
        candidates = result.scalars().all()

        for customer in candidates:
            customer_realms = [
                r.strip() for r in customer.realms.split(",") if r.strip()
            ]
            if realm in customer_realms:
                return customer.as_dict()

        return {}


async def customer_get(customer_id: int) -> Optional[dict]:
    """
    Get a customer by id.

    Parameters:
        customer_id (int): The ID of the customer to retrieve.

    Returns:
        Optional[dict]: Dictionary representation of the customer if found, else empty dict.
    """

    async with get_async_session() as session:
        result = await session.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        if not (customer := result.scalars().first()):
            return {}

        return customer.as_dict()


async def customer_get_by_partner_id(partner_id: str) -> Optional[dict]:
    """
    Get a customer by partner_id.

    Parameters:
        partner_id (str): The partner ID of the customer to retrieve.

    Returns:
        Optional[dict]: Dictionary representation of the customer if found, else empty dict.
    """

    async with get_async_session() as session:
        result = await session.execute(
            select(Customer).where(Customer.partner_id == partner_id)
        )
        if not (customer := result.scalars().first()):
            return {}

        return customer.as_dict()


async def customer_get_all(admin_user: dict) -> list[dict]:
    """
    Get all customers.

    Parameters:
        admin_user (dict): Dictionary containing admin user details, including 'bofh' and 'realm' keys.

    Returns:
        list[dict]: List of dictionary representations of customers.
    """

    async with get_async_session() as session:
        if admin_user["bofh"]:
            result = await session.execute(select(Customer))
            customers = result.scalars().all()
            return [customer.as_dict() for customer in customers]
        elif admin_user["admin"]:
            realm = admin_user["realm"]
            # Pre-filter with SQL LIKE, then verify exact match
            result = await session.execute(
                select(Customer).where(Customer.realms.like(f"%{realm}%"))
            )
            candidates = result.scalars().all()
            matching_customers = []

            for customer in candidates:
                customer_realms = [
                    r.strip() for r in customer.realms.split(",") if r.strip()
                ]

                if realm in customer_realms:
                    matching_customers.append(customer.as_dict())

            return matching_customers

        else:
            return []


async def customer_update(
    customer_id: Optional[int] = None,
    customer_abbr: Optional[str] = None,
    partner_id: Optional[str] = None,
    name: Optional[str] = None,
    contact_email: Optional[str] = None,
    support_contact_email: Optional[str] = None,
    priceplan: Optional[str] = None,
    base_fee: Optional[int] = None,
    realms: Optional[str] = None,
    notes: Optional[str] = None,
    blocks_purchased: Optional[int] = None,
) -> Optional[dict]:
    """
    Update customer metadata.

    Parameters:
        customer_id (Optional[int]): The ID of the customer to update.
        customer_abbr (Optional[str]): New abbreviation for the customer.
        partner_id (Optional[str]): New partner ID for the customer.
        name (Optional[str]): New name for the customer.
        contact_email (Optional[str]): New contact email for the customer.
        support_contact_email (Optional[str]): New support contact email for end users.
        priceplan (Optional[str]): New pricing plan for the customer.
        base_fee (Optional[int]): New base fee for the customer.
        realms (Optional[str]): New comma-separated list of realms for the customer.
        notes (Optional[str]): New notes for the customer.
        blocks_purchased (Optional[int]): New number of blocks purchased.

    Returns:
        Optional[dict]: Dictionary representation of the updated customer if found, else empty dict.
    """

    async with get_async_session() as session:
        result = await session.execute(
            select(Customer).where(Customer.id == customer_id).with_for_update()
        )
        if not (customer := result.scalars().first()):
            return {}

        if customer_abbr is not None:
            customer.customer_abbr = customer_abbr
        if partner_id is not None:
            customer.partner_id = partner_id
        if name is not None:
            customer.name = name
        if contact_email is not None:
            customer.contact_email = contact_email
        if support_contact_email is not None:
            customer.support_contact_email = support_contact_email
        if priceplan is not None:
            customer.priceplan = priceplan
        if base_fee is not None:
            customer.base_fee = base_fee
        if realms is not None:
            customer.realms = realms
        if notes is not None:
            customer.notes = notes
        if blocks_purchased is not None:
            customer.blocks_purchased = blocks_purchased

        log.info(f"Customer {customer.name} (ID: {customer.id}) updated.")

        return customer.as_dict()


async def customer_delete(customer_id: int) -> bool:
    """
    Delete a customer by id.

    Parameters:
        customer_id (int): The ID of the customer to delete.

    Returns:
        bool: True if the customer was deleted, False if not found.
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        if not (customer := result.scalars().first()):
            return False

        session.delete(customer)

    log.info(f"Customer {customer.name} (ID: {customer.id}) deleted.")

    return True


async def customer_get_statistics(customer_id: int) -> dict:
    """
    Get statistics for a specific customer.
    Calculates transcription statistics for all users in the customer's realms.
    For fixed plan customers, calculates block usage and overages.

    Parameters:
        customer_id (int): The ID of the customer to get statistics for.

    Returns:
        dict: Dictionary containing customer statistics.
    """

    async with get_async_session() as session:
        result = await session.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        if not (customer := result.scalars().first()):
            return {
                "total_users": 0,
                "transcribed_files": 0,
                "transcribed_files_last_month": 0,
                "transcribed_minutes": 0,
                "transcribed_minutes_external": 0,
                "transcribed_minutes_last_month": 0,
                "transcribed_minutes_external_last_month": 0,  # REACH etc
                "total_transcribed_minutes": 0,
                "total_transcribed_minutes_last_month": 0,
                "blocks_purchased": 0,
                "blocks_consumed": 0,
                "minutes_included": 0,
                "overage_minutes": 0,
                "overage_minutes_last_month": 0,
                "remaining_minutes": 0,
            }

        # Get all users associated with this customer's realms
        if not (
            realm_list := [r.strip() for r in customer.realms.split(",") if r.strip()]
        ):
            return {
                "total_users": 0,
                "transcribed_files": 0,
                "transcribed_minutes": 0,
                "transcribed_minutes_external": 0,
                "transcribed_minutes_last_month": 0,
                "transcribed_minutes_external_last_month": 0,  # REACH etc
                "transcribed_files_last_month": 0,
                "total_transcribed_minutes": 0,
                "total_transcribed_minutes_last_month": 0,
                "blocks_purchased": (
                    customer.blocks_purchased if customer.blocks_purchased else 0
                ),
                "blocks_consumed": 0,
                "minutes_included": (
                    customer.blocks_purchased if customer.blocks_purchased else 0
                )
                * settings.CUSTOMER_MINUTES_PER_BLOCK,
                "overage_minutes": 0,
                "overage_minutes_last_month": 0,
                "remaining_minutes": (
                    customer.blocks_purchased if customer.blocks_purchased else 0
                )
                * settings.CUSTOMER_MINUTES_PER_BLOCK,
            }

        result = await session.execute(
            select(User).where(User.realm.in_(realm_list))
        )
        users = list(result.scalars().all())

        result = await session.execute(
            select(User).where(User.username == customer.partner_id)
        )
        partner_users = result.scalars().all()

        users.extend(partner_users)

        transcribed_minutes = 0
        transcribed_minutes_external = 0
        transcribed_minutes_last_month = 0
        transcribed_minutes_external_last_month = 0  # REACH etc

        total_transcribed_minutes_current = 0
        total_transcribed_minutes_last = 0
        total_files_current = 0
        total_files_last = 0

        today = datetime.now(UTC).date()
        first_day_this_month = today.replace(day=1)
        last_day_prev_month = first_day_this_month - timedelta(days=1)
        first_day_prev_month = last_day_prev_month.replace(day=1)

        # Batch-fetch all jobs for all users in one query instead of N+1
        user_ids = [user.user_id for user in users]
        if user_ids:
            result = await session.execute(
                select(Job).where(
                    Job.user_id.in_(user_ids),
                    Job.job_type == JobType.TRANSCRIPTION,
                    Job.created_at >= first_day_prev_month,
                )
            )
            all_jobs = result.scalars().all()
        else:
            all_jobs = []

        # Build user_id -> User mapping for username checks
        user_map = {user.user_id: user for user in users}

        for job in all_jobs:
            job_date = job.created_at.date()
            user = user_map.get(job.user_id)
            is_external = user.username.isnumeric() if user else False

            if job.status in ("completed", "deleted"):
                transcribed_seconds = job.transcribed_seconds or 0

                if job_date >= first_day_this_month:
                    total_files_current += 1
                    total_transcribed_minutes_current += transcribed_seconds / 60

                    if is_external:
                        transcribed_minutes_external += transcribed_seconds / 60
                    else:
                        transcribed_minutes += transcribed_seconds / 60

                elif first_day_prev_month <= job_date <= last_day_prev_month:
                    total_files_last += 1
                    total_transcribed_minutes_last += transcribed_seconds / 60

                    if is_external:
                        transcribed_minutes_external_last_month += (
                            transcribed_seconds / 60
                        )
                    else:
                        transcribed_minutes_last_month += transcribed_seconds / 60

        # Calculate block usage for fixed plan customers
        blocks_purchased = customer.blocks_purchased if customer.blocks_purchased else 0
        minutes_included = blocks_purchased * settings.CUSTOMER_MINUTES_PER_BLOCK

        blocks_consumed = 0
        overage_minutes = 0
        overage_minutes_last_month = 0
        remaining_minutes = 0

        if customer.priceplan == "fixed" and blocks_purchased > 0:
            if total_transcribed_minutes_current > minutes_included:
                blocks_consumed = blocks_purchased
                overage_minutes = total_transcribed_minutes_current - minutes_included
                remaining_minutes = 0
            else:
                # Calculate partial blocks consumed
                blocks_consumed = (
                    total_transcribed_minutes_current
                    / settings.CUSTOMER_MINUTES_PER_BLOCK
                )
                remaining_minutes = minutes_included - total_transcribed_minutes_current

            if transcribed_minutes_last_month > 4000 * blocks_purchased:
                overage_minutes_last_month = total_transcribed_minutes_last - (
                    4000 * blocks_purchased
                )

        return {
            "total_users": len(users),
            "transcribed_files": int(total_files_current),
            "transcribed_files_last_month": int(total_files_last),
            "transcribed_minutes": int(transcribed_minutes),
            "transcribed_minutes_external": int(transcribed_minutes_external),
            "transcribed_minutes_last_month": int(transcribed_minutes_last_month),
            "transcribed_minutes_external_last_month": int(
                transcribed_minutes_external_last_month
            ),
            "total_transcribed_minutes": int(total_transcribed_minutes_current),
            "total_transcribed_minutes_last_month": int(total_transcribed_minutes_last),
            "blocks_purchased": blocks_purchased,
            "blocks_consumed": round(blocks_consumed, 2),
            "minutes_included": minutes_included,
            "overage_minutes": int(overage_minutes),
            "overage_minutes_last_month": int(overage_minutes_last_month),
            "remaining_minutes": int(remaining_minutes),
        }


async def get_all_realms() -> list[str]:
    """
    Get all unique realms from users.
    Returns a sorted list of unique realm strings.

    Parameters:
        None

    Returns:
        list[str]: Sorted list of unique realms.
    """
    async with get_async_session() as session:
        result = await session.execute(select(User.realm).distinct())
        realms = result.all()
        realm_list = [realm[0] for realm in realms if realm[0]]

        return sorted(realm_list)


async def _customers_matching_realm(session, realm: str) -> list:
    """Return customers whose realms field contains the given realm."""
    result = await session.execute(
        select(Customer).where(Customer.realms.like(f"%{realm}%"))
    )
    return result.scalars().all()


async def get_customer_name_from_realm(realm: str) -> Optional[str]:
    """
    Get customer name from a realm.
    Returns the customer name if the realm is associated with a customer.

    Parameters:
        realm (str): The realm string to search for.

    Returns:
        Optional[str]: Customer name if found, else None.
    """
    async with get_async_session() as session:
        for customer in await _customers_matching_realm(session, realm):
            customer_realms = [
                r.strip() for r in customer.realms.split(",") if r.strip()
            ]
            if realm in customer_realms:
                return customer.name

        return None


async def get_customer_by_realm(realm: str) -> Optional[dict]:
    """
    Get customer details by realm.
    Returns the first customer that has this realm in their realms list.

    Parameters:
        realm (str): The realm string to search for.

    Returns:
        Optional[dict]: Customer dictionary if found, else None.
    """
    async with get_async_session() as session:
        for customer in await _customers_matching_realm(session, realm):
            customer_realms = [
                r.strip() for r in customer.realms.split(",") if r.strip()
            ]
            if realm in customer_realms:
                return customer.as_dict()

        return None


async def customer_list_by_realms(realms: list[str]) -> list[dict]:
    """
    Get all customers that have any of the specified realms.

    Parameters:
        realms: List of realm strings to search for

    Returns:
        List of customer dictionaries
    """
    async with get_async_session() as session:
        # Pre-filter with SQL LIKE to reduce rows fetched
        conditions = [Customer.realms.like(f"%{realm}%") for realm in realms]
        if conditions:
            result = await session.execute(
                select(Customer).where(or_(*conditions))
            )
            customers = result.scalars().all()
        else:
            customers = []

        matching_customers = []
        for customer in customers:
            customer_realms = [
                r.strip() for r in customer.realms.split(",") if r.strip()
            ]
            if any(realm in customer_realms for realm in realms):
                matching_customers.append(customer.as_dict())

        return matching_customers


async def export_customers_to_csv(admin_user: dict) -> str:
    """
    Export all customers with their statistics to CSV format.

    Parameters:
        admin_user (dict): Dictionary containing admin user details.

    Returns:
        CSV string with customer data and statistics
    """

    output = io.StringIO()

    if not (customers := await customer_get_all(admin_user)):
        return ""

    now = datetime.now()
    this_month = now.strftime("%y-%m")
    last_month = (now.replace(day=1) - timedelta(days=1)).strftime("%y-%m")

    # Define CSV headers
    fieldnames = [
        "Customer Name",
        "Customer Abbreviation",
        "Partner ID",
        "Contact Email",
        "Price Plan",
        "Base Fee",
        "Blocks Purchased",
        "Realms",
        "Total Users",
        f"Files ({this_month})",
        f"Files ({last_month})",
        f"Total minutes ({this_month})",
        f"Total minutes ({last_month})",
        f"Minutes via Sunet Play ({this_month})",
        f"Minutes via Sunet Play ({last_month})",
        f"Minutes via web interface and API ({this_month})",
        f"Minutes via web interface and API ({last_month})",
        "Blocks Consumed",
        "Minutes Included",
        "Overage Minutes",
        f"Overage Minutes ({last_month})",
        "Remaining Minutes",
        "Notes",
        "Created At",
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for customer in customers:
        stats = await customer_get_statistics(customer["id"])

        row = {
            "Customer Name": customer.get("name", ""),
            "Customer Abbreviation": customer.get("customer_abbr", ""),
            "Partner ID": customer.get("partner_id", ""),
            "Contact Email": customer.get("contact_email", ""),
            "Price Plan": customer.get("priceplan", "").capitalize(),
            "Base Fee": customer.get("base_fee", 0),
            "Blocks Purchased": customer.get("blocks_purchased", 0),
            "Realms": customer.get("realms", ""),
            "Total Users": stats.get("total_users", 0),
            f"Files ({this_month})": stats.get("transcribed_files", 0),
            f"Files ({last_month})": stats.get("transcribed_files_last_month", 0),
            f"Total minutes ({this_month})": stats.get("total_transcribed_minutes", 0),
            f"Total minutes ({last_month})": stats.get(
                "total_transcribed_minutes_last_month", 0
            ),
            f"Minutes via Sunet Play ({this_month})": stats.get(
                "transcribed_minutes_external", 0
            ),
            f"Minutes via Sunet Play ({last_month})": stats.get(
                "transcribed_minutes_external_last_month", 0
            ),
            f"Minutes via web interface and API ({this_month})": stats.get(
                "transcribed_minutes", 0
            ),
            f"Minutes via web interface and API ({last_month})": stats.get(
                "transcribed_minutes_last_month", 0
            ),
            "Blocks Consumed": stats.get("blocks_consumed", 0),
            "Minutes Included": stats.get("minutes_included", 0),
            "Overage Minutes": stats.get("overage_minutes", 0),
            f"Overage Minutes ({last_month})": stats.get(
                "overage_minutes_last_month", 0
            ),
            "Remaining Minutes": stats.get("remaining_minutes", 0),
            "Notes": customer.get("notes", ""),
            "Created At": customer.get("created_at", ""),
        }

        writer.writerow(row)

    return output.getvalue()


def _customer_get_statistics_sync(customer_id: int) -> dict:
    """Sync version of customer_get_statistics for APScheduler background tasks."""

    with get_session() as session:
        customer = (
            session.query(Customer)
            .filter(Customer.id == customer_id)
            .first()
        )

        if not customer:
            return {
                "total_users": 0,
                "transcribed_files": 0,
                "transcribed_files_last_month": 0,
                "transcribed_minutes": 0,
                "transcribed_minutes_external": 0,
                "transcribed_minutes_last_month": 0,
                "transcribed_minutes_external_last_month": 0,
                "total_transcribed_minutes": 0,
                "total_transcribed_minutes_last_month": 0,
                "blocks_purchased": 0,
                "blocks_consumed": 0,
                "minutes_included": 0,
                "overage_minutes": 0,
                "overage_minutes_last_month": 0,
                "remaining_minutes": 0,
            }

        if not (
            realm_list := [r.strip() for r in customer.realms.split(",") if r.strip()]
        ):
            blocks = customer.blocks_purchased if customer.blocks_purchased else 0
            mins = blocks * settings.CUSTOMER_MINUTES_PER_BLOCK
            return {
                "total_users": 0,
                "transcribed_files": 0,
                "transcribed_minutes": 0,
                "transcribed_minutes_external": 0,
                "transcribed_minutes_last_month": 0,
                "transcribed_minutes_external_last_month": 0,
                "transcribed_files_last_month": 0,
                "total_transcribed_minutes": 0,
                "total_transcribed_minutes_last_month": 0,
                "blocks_purchased": blocks,
                "blocks_consumed": 0,
                "minutes_included": mins,
                "overage_minutes": 0,
                "overage_minutes_last_month": 0,
                "remaining_minutes": mins,
            }

        users = session.query(User).filter(User.realm.in_(realm_list)).all()
        partner_users = (
            session.query(User).filter(User.username == customer.partner_id).all()
        )
        users.extend(partner_users)

        transcribed_minutes = 0
        transcribed_minutes_external = 0
        transcribed_minutes_last_month = 0
        transcribed_minutes_external_last_month = 0

        total_transcribed_minutes_current = 0
        total_transcribed_minutes_last = 0
        total_files_current = 0
        total_files_last = 0

        today = datetime.now(UTC).date()
        first_day_this_month = today.replace(day=1)
        last_day_prev_month = first_day_this_month - timedelta(days=1)
        first_day_prev_month = last_day_prev_month.replace(day=1)

        user_ids = [user.user_id for user in users]
        all_jobs = (
            session.query(Job)
            .filter(
                Job.user_id.in_(user_ids),
                Job.job_type == JobType.TRANSCRIPTION,
                Job.created_at >= first_day_prev_month,
            )
            .all()
        ) if user_ids else []

        user_map = {user.user_id: user for user in users}

        for job in all_jobs:
            job_date = job.created_at.date()
            user = user_map.get(job.user_id)
            is_external = user.username.isnumeric() if user else False

            if job.status in ("completed", "deleted"):
                transcribed_seconds = job.transcribed_seconds or 0

                if job_date >= first_day_this_month:
                    total_files_current += 1
                    total_transcribed_minutes_current += transcribed_seconds / 60
                    if is_external:
                        transcribed_minutes_external += transcribed_seconds / 60
                    else:
                        transcribed_minutes += transcribed_seconds / 60
                elif first_day_prev_month <= job_date <= last_day_prev_month:
                    total_files_last += 1
                    total_transcribed_minutes_last += transcribed_seconds / 60
                    if is_external:
                        transcribed_minutes_external_last_month += transcribed_seconds / 60
                    else:
                        transcribed_minutes_last_month += transcribed_seconds / 60

        blocks_purchased = customer.blocks_purchased if customer.blocks_purchased else 0
        minutes_included = blocks_purchased * settings.CUSTOMER_MINUTES_PER_BLOCK
        blocks_consumed = 0
        overage_minutes = 0
        overage_minutes_last_month = 0
        remaining_minutes = 0

        if customer.priceplan == "fixed" and blocks_purchased > 0:
            if total_transcribed_minutes_current > minutes_included:
                blocks_consumed = blocks_purchased
                overage_minutes = total_transcribed_minutes_current - minutes_included
                remaining_minutes = 0
            else:
                blocks_consumed = (
                    total_transcribed_minutes_current / settings.CUSTOMER_MINUTES_PER_BLOCK
                )
                remaining_minutes = minutes_included - total_transcribed_minutes_current
            if transcribed_minutes_last_month > 4000 * blocks_purchased:
                overage_minutes_last_month = total_transcribed_minutes_last - (
                    4000 * blocks_purchased
                )

        return {
            "total_users": len(users),
            "transcribed_files": int(total_files_current),
            "transcribed_files_last_month": int(total_files_last),
            "transcribed_minutes": int(transcribed_minutes),
            "transcribed_minutes_external": int(transcribed_minutes_external),
            "transcribed_minutes_last_month": int(transcribed_minutes_last_month),
            "transcribed_minutes_external_last_month": int(transcribed_minutes_external_last_month),
            "total_transcribed_minutes": int(total_transcribed_minutes_current),
            "total_transcribed_minutes_last_month": int(total_transcribed_minutes_last),
            "blocks_purchased": blocks_purchased,
            "blocks_consumed": round(blocks_consumed, 2),
            "minutes_included": minutes_included,
            "overage_minutes": int(overage_minutes),
            "overage_minutes_last_month": int(overage_minutes_last_month),
            "remaining_minutes": int(remaining_minutes),
        }


def check_quota_alerts() -> None:
    """
    Check all fixed-plan customers for 95%+ block quota consumption.
    Sends email alerts to admin users who have the quota notification enabled.

    Returns:
        None
    """

    with get_session() as session:
        customers = (
            session.query(Customer)
            .filter(
                Customer.priceplan == "fixed",
                Customer.blocks_purchased > 0,
            )
            .all()
        )

        for customer in customers:
            stats = _customer_get_statistics_sync(customer.id)
            minutes_included = stats.get("minutes_included", 0)

            if minutes_included == 0:
                continue

            minutes_consumed = stats.get("total_transcribed_minutes", 0)
            usage_percent = int((minutes_consumed / minutes_included) * 100)

            if usage_percent < 95:
                continue

            realm_list = [r.strip() for r in customer.realms.split(",") if r.strip()]

            for realm in realm_list:
                admin_users = (
                    session.query(User)
                    .filter(
                        User.admin == True,  # noqa: E712
                        User.deleted == False,  # noqa: E712
                        User.admin_domains.ilike(f"%{realm}%"),
                    )
                    .all()
                )

                for admin_user in admin_users:
                    if (
                        not admin_user.notifications
                        or "quota" not in admin_user.notifications.split(",")
                    ):
                        continue

                    if not admin_user.email:
                        continue

                    if notifications.notification_sent_record_exists(
                        admin_user.user_id, str(customer.id), "quota_alert"
                    ):
                        continue

                    notifications.send_quota_alert(
                        to_email=admin_user.email,
                        customer_name=customer.name,
                        usage_percent=usage_percent,
                        blocks_purchased=stats.get("blocks_purchased", 0),
                        minutes_included=minutes_included,
                        minutes_consumed=minutes_consumed,
                        remaining_minutes=stats.get("remaining_minutes", 0),
                    )

                    notifications.notification_sent_record_add(
                        admin_user.user_id, str(customer.id), "quota_alert"
                    )

                    log.info(
                        f"Quota alert sent to {admin_user.email} for customer {customer.name} ({usage_percent}%)"
                    )


def send_weekly_usage_reports() -> None:
    """
    Send weekly usage reports to admin users who have the weekly report notification enabled.

    Returns:
        None
    """

    with get_session() as session:
        customers = session.query(Customer).all()

        # Fetch admin users once instead of per-realm
        admin_users = (
            session.query(User)
            .filter(User.admin == True, User.deleted == False, User.admin_domains != None)  # noqa: E712
            .all()
        )

        # Build admin domain -> users mapping
        admin_by_domain = {}
        for user in admin_users:
            for domain in user.admin_domains.split(","):
                domain = domain.strip()
                if domain:
                    admin_by_domain.setdefault(domain, []).append(user)

        # Build customer id -> customer mapping
        customer_map = {c.id: c for c in customers}

        # Build a mapping of admin user -> list of customers they manage
        admin_customer_map = {}  # user_id -> (user, set of customer ids)

        for customer in customers:
            realm_list = [r.strip() for r in customer.realms.split(",") if r.strip()]

            for realm in realm_list:
                for user in admin_by_domain.get(realm, []):
                    if user.user_id not in admin_customer_map:
                        admin_customer_map[user.user_id] = (user, set())
                    admin_customer_map[user.user_id][1].add(customer.id)

        # Send one email per admin user with aggregated stats
        for user_id, (admin_user, customer_ids) in admin_customer_map.items():
            if (
                not admin_user.notifications
                or "weekly_report" not in admin_user.notifications.split(",")
            ):
                continue

            if not admin_user.email:
                continue

            customer_names = []
            totals = {
                "total_users": 0,
                "transcribed_files": 0,
                "transcribed_minutes": 0,
                "transcribed_minutes_external": 0,
                "blocks_purchased": 0,
                "blocks_consumed": 0,
                "minutes_included": 0,
                "remaining_minutes": 0,
                "overage_minutes": 0,
            }

            for cid in customer_ids:
                cust = customer_map.get(cid)
                if cust:
                    customer_names.append(cust.name)
                stats = _customer_get_statistics_sync(cid)
                for key in totals:
                    totals[key] += stats.get(key, 0)

            notifications.send_weekly_usage_report(
                to_email=admin_user.email,
                customer_name=", ".join(sorted(customer_names)),
                total_users=totals["total_users"],
                transcribed_files=totals["transcribed_files"],
                transcribed_minutes=totals["transcribed_minutes"],
                transcribed_minutes_external=totals["transcribed_minutes_external"],
                blocks_purchased=totals["blocks_purchased"],
                blocks_consumed=totals["blocks_consumed"],
                minutes_included=totals["minutes_included"],
                remaining_minutes=totals["remaining_minutes"],
                overage_minutes=totals["overage_minutes"],
            )

            log.info(
                f"Weekly usage report sent to {admin_user.email} for customers: {', '.join(sorted(customer_names))}"
            )
