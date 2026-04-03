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

import json

from datetime import datetime, timedelta
from db.models import (
    Job,
    JobResult,
    JobStatusEnum,
    JobType,
    Jobs,
    OutputFormatEnum,
    User,
)
from db.session import get_async_session, get_session
from pathlib import Path
from sqlalchemy import select
from typing import Optional
from utils.log import get_logger
from utils.settings import get_settings
from utils.notifications import notifications
from db.models import GroupUserLink

log = get_logger()
settings = get_settings()


async def job_create(
    user_id: Optional[str] = None,
    job_type: Optional[JobStatusEnum] = None,
    language: Optional[str] = "",
    model_type: Optional[str] = "",
    filename: Optional[str] = "",
    output_format: Optional[str] = None,
    external_id: Optional[str] = None,
    external_user_id: Optional[str] = None,
    billing_id: Optional[str] = None,
    client_dn: Optional[str] = None,
) -> dict:
    """
    Create a new job in the database.

    Parameters:
        user_id (str): The ID of the user creating the job.
        job_type (JobType): The type of job being created.
        language (str): The language of the job.
        model_type (str): The model type for the job.
        filename (str): The filename associated with the job.
        output_format (OutputFormatEnum): The desired output format for the job.
        external_id (str): An external ID associated with the job.
        external_user_id (str): An external user ID associated with the job.
        billing_id (str): A billing ID associated with the job.
        client_dn (str): The client distinguished name.

    Returns:
        dict: The created job as a dictionary.
    """

    async with get_async_session() as session:
        job = Job(
            user_id=user_id,
            job_type=job_type,
            language=language,
            model_type=model_type,
            status=JobStatusEnum.UPLOADING,
            filename=filename,
            output_format=output_format,
            external_id=external_id,
            external_user_id=external_user_id,
            billing_id=billing_id,
            client_dn=client_dn,
        )

        session.add(job)

        log.info(f"Job {job.uuid} created for user {user_id}.")

        return job.as_dict()


async def job_get(uuid: str, user_id: str) -> Optional[Job]:
    """
    Get a job by UUID.

    Parameters:
        uuid (str): The UUID of the job to retrieve.
        user_id (str): The ID of the user requesting the job.

    Returns:
        dict: The job as a dictionary if found, otherwise an empty dictionary.
    """

    async with get_async_session() as session:
        result = await session.execute(
            select(Job).where(Job.uuid == uuid).where(Job.user_id == user_id)
        )
        job = result.scalars().first()

        return job.as_dict() if job else {}


async def job_get_by_external_id(external_id: str, client_dn: str) -> Optional[Job]:
    """
    Get a job by External ID.

    Parameters:
        external_id (str): The external ID of the job to retrieve.
        client_dn (str): The client distinguished name.

    Returns:
        dict: The job as a dictionary if found, otherwise an empty dictionary.
    """
    async with get_async_session() as session:
        result = await session.execute(
            select(Job).where(Job.external_id == external_id)
            # .where(Job.client_dn == client_dn)
        )
        job = result.scalars().first()

        return job.as_dict() if job else {}


async def job_get_next() -> dict:
    """
    Get the next available job from the database.

    Returns:
        dict: The next job as a dictionary if found, otherwise an empty dictionary.
    """

    async with get_async_session() as session:
        result = await session.execute(
            select(Job)
            .where(Job.status == JobStatusEnum.PENDING)
            .with_for_update()
        )
        job = result.scalars().first()

        if job:
            job.status = JobStatusEnum.IN_PROGRESS

        return job.as_dict() if job else {}


async def job_get_all(user_id: str, cleaned: Optional[bool] = False) -> list[Job]:
    """
    Get all jobs from the database.

    Parameters:
        user_id (str): The ID of the user requesting the jobs.
        cleaned (bool): Whether to include jobs with empty filenames.

    Returns:
        dict: A dictionary containing a list of jobs.
    """

    async with get_async_session() as session:
        if cleaned:
            result = await session.execute(
                select(Job)
                .where(Job.user_id == user_id)
                .where(Job.job_type == JobType.TRANSCRIPTION)
            )
        else:
            result = await session.execute(
                select(Job)
                .where(Job.user_id == user_id)
                .where(Job.job_type == JobType.TRANSCRIPTION)
                .where(Job.filename != "")
            )

        jobs = result.scalars().all()

        if not jobs:
            return {"jobs": []}

        return {"jobs": [job.as_dict() for job in jobs]}


async def job_get_status(user_id: str) -> dict:
    """
    Get all job UUIDs together with statuses from the database.

    Parameters:
        user_id (str): The ID of the user requesting the jobs.

    Returns:
        dict: A dictionary containing a list of jobs with their statuses.
    """

    async with get_async_session() as session:
        columns = [Job.uuid, Job.status, Job.job_type, Job.created_at, Job.updated_at]

        result = await session.execute(
            select(*columns).where(Job.user_id == user_id)
        )
        query = result.all()

        if not query:
            return {}

        jobs = [job for job in query]

        return Jobs(jobs=jobs)


async def job_update(
    uuid: str,
    user_id: Optional[str] = None,
    status: Optional[JobStatusEnum] = None,
    language: Optional[str] = None,
    model_type: Optional[str] = None,
    speakers: Optional[int] = None,
    error: Optional[str] = None,
    output_format: Optional[str] = None,
    transcribed_seconds: Optional[int] = 0,
) -> Optional[Job]:
    """
    Update a job by UUID.

    Parameters:
        uuid (str): The UUID of the job to update.
        user_id (str): The ID of the user associated with the job.
        status (JobStatusEnum): The new status of the job.
        language (str): The language of the job.
        model_type (str): The model type for the job.
        speakers (int): The number of speakers in the job.
        error (str): An error message associated with the job.
        output_format (OutputFormatEnum): The desired output format for the job.
        transcribed_seconds (int): The number of transcribed seconds.

    Returns:
        dict: The updated job as a dictionary if found, otherwise None.
    """

    async with get_async_session() as session:
        stmt = select(Job).where(Job.uuid == uuid)
        if user_id:
            stmt = stmt.where(Job.user_id == user_id)
        stmt = stmt.with_for_update()

        result = await session.execute(stmt)
        job = result.scalars().first()

        if not job:
            return None
        if status:
            job.status = status
        if error:
            job.error = error
        if language:
            job.language = language
        if model_type:
            job.model_type = model_type
        if speakers:
            job.speakers = str(speakers)
        if output_format:
            job.output_format = output_format
        if transcribed_seconds:
            job.transcribed_seconds = transcribed_seconds

        log.info(f"Job {job.uuid} updated for user {user_id}.")

        return job.as_dict()


async def job_remove(uuid: str) -> bool:
    """
    Delete a job by UUID.

    Parameters:
        uuid (str): The UUID of the job to delete.

    Returns:
        bool: True if the job was deleted, False otherwise.
    """

    async with get_async_session() as session:
        result = await session.execute(
            select(Job).where(Job.uuid == uuid).with_for_update()
        )
        job = result.scalars().first()

        if not job:
            return False

        file_path = Path(settings.API_FILE_STORAGE_DIR) / job.user_id / job.uuid
        file_path_mp4 = (
            Path(settings.API_FILE_STORAGE_DIR) / job.user_id / f"{job.uuid}.mp4"
        )
        file_path_mp4_enc = (
            Path(settings.API_FILE_STORAGE_DIR) / job.user_id / f"{job.uuid}.mp4.enc"
        )
        file_path_enc = (
            Path(settings.API_FILE_STORAGE_DIR) / job.user_id / f"{job.uuid}.enc"
        )

        if file_path.exists():
            file_path.unlink()

        if file_path_mp4.exists():
            file_path_mp4.unlink()

        if file_path_enc.exists():
            file_path_enc.unlink()

        if file_path_mp4_enc.exists():
            file_path_mp4_enc.unlink()

        # Anonymize job data instead of deleting the record.
        # We keep the record for auditing and billing purposes.
        job.job_type = "transcription"
        job.language = ""
        job.model_type = ""
        job.filename = ""
        job.error = ""
        job.speakers = "0"
        job.status = JobStatusEnum.DELETED
        job.output_format = OutputFormatEnum.NONE

        # Remove JobResult associated with the job
        result = await session.execute(
            select(JobResult)
            .where(JobResult.job_id == uuid)
            .with_for_update()
        )
        job_results = result.scalars().all()

        # Delete associated job results.
        for result in job_results:
            log.info(
                f"Job result for job {result.job_id} created at {result.created_at} removed for user {result.user_id}."
            )
            await session.delete(result)

    return True


def user_purge_deleted() -> None:
    """
    Hard-delete soft-deleted users that have no remaining jobs or job results.
    Intended to be called from job_cleanup() after jobs have been purged.
    """
    from sqlalchemy import exists

    with get_session() as session:
        # Find deleted users that have no jobs and no job results in one query
        job_exists = exists().where(Job.user_id == User.user_id)
        result_exists = exists().where(JobResult.user_id == User.user_id)

        purgeable_users = (
            session.query(User)
            .filter(
                User.deleted == True,  # noqa: E712
                ~job_exists,
                ~result_exists,
            )
            .all()
        )

        for user in purgeable_users:
            session.query(GroupUserLink).filter(
                GroupUserLink.user_id == user.id
            ).delete()
            session.delete(user)
            log.info(
                f"User {user.user_id} permanently deleted (no remaining data)."
            )


def job_cleanup() -> None:
    """
    Remove all jobs from the database.

    This function performs two main tasks:
    1. It cleans up jobs that have reached their deletion date by invoking the
       `job_remove` function for each of these jobs.
    2. It permanently deletes jobs that were created more than approximately
         two months ago (62 days) from the database.

    Returns:
        None
    """

    with get_session() as session:
        # Cleanup jobs older than deletion date
        jobs_to_cleanup = (
            session.query(Job).filter(Job.deletion_date <= datetime.now()).all()
        )

        # Notify about jobs that will be deleted tomorrow
        jobs_to_notify = (
            session.query(Job)
            .filter(Job.deletion_date <= datetime.now() + timedelta(days=1))
            .filter(Job.status != JobStatusEnum.DELETED)
            .all()
        )

        # Pre-fetch all relevant users in one query instead of per-job lookups
        all_user_ids = {job.user_id for job in jobs_to_cleanup + jobs_to_notify}
        users_map = {}
        if all_user_ids:
            user_rows = session.query(User).filter(User.user_id.in_(all_user_ids)).all()
            users_map = {u.user_id: u for u in user_rows}

        for job in jobs_to_cleanup:
            # Inline job removal logic (job_remove is now async)
            file_path = Path(settings.API_FILE_STORAGE_DIR) / job.user_id / job.uuid
            file_path_mp4 = (
                Path(settings.API_FILE_STORAGE_DIR) / job.user_id / f"{job.uuid}.mp4"
            )
            file_path_mp4_enc = (
                Path(settings.API_FILE_STORAGE_DIR) / job.user_id / f"{job.uuid}.mp4.enc"
            )
            file_path_enc = (
                Path(settings.API_FILE_STORAGE_DIR) / job.user_id / f"{job.uuid}.enc"
            )

            if file_path.exists():
                file_path.unlink()

            if file_path_mp4.exists():
                file_path_mp4.unlink()

            if file_path_enc.exists():
                file_path_enc.unlink()

            if file_path_mp4_enc.exists():
                file_path_mp4_enc.unlink()

            # Anonymize job data instead of deleting the record.
            # We keep the record for auditing and billing purposes.
            job.job_type = "transcription"
            job.language = ""
            job.model_type = ""
            job.filename = ""
            job.error = ""
            job.speakers = "0"
            job.status = JobStatusEnum.DELETED
            job.output_format = OutputFormatEnum.NONE

            # Remove JobResult associated with the job
            job_results = (
                session.query(JobResult)
                .filter(JobResult.job_id == job.uuid)
                .with_for_update()
                .all()
            )

            # Delete associated job results.
            for result in job_results:
                log.info(
                    f"Job result for job {result.job_id} created at {result.created_at} removed for user {result.user_id}."
                )
                session.delete(result)

            if job.status == JobStatusEnum.DELETED:
                continue

            user = users_map.get(job.user_id)

            if not user or not user.notifications:
                continue

            if "deletion" not in user.notifications.split(","):
                continue

            if user.email == "":
                continue

            if notifications.notification_sent_record_exists(
                user.user_id, job.uuid, "deletion"
            ):
                continue

            log.info(
                f"Sending transcription deletion notification to user {user.user_id} for job {job.uuid}."
            )

            notifications.send_job_deleted(user.email)
            notifications.notification_sent_record_add(
                user.user_id, job.uuid, "deletion"
            )

        # Permanently delete all jobs older than ~2 months
        jobs_to_delete = (
            session.query(Job)
            .filter(Job.created_at <= datetime.now() - timedelta(days=62))
            .all()
        )

        for job in jobs_to_delete:
            # Nuke the record since we don't need it anymore.
            # Results etc should have been deleted already.
            log.info(
                f"Permanently deleting job {job.uuid} created at {job.created_at} from database."
            )
            session.delete(job)

        for job in jobs_to_notify:
            user = users_map.get(job.user_id)

            if not user or not user.notifications:
                continue

            if "deletion" not in user.notifications.split(","):
                continue

            if user.email == "":
                continue

            if notifications.notification_sent_record_exists(
                user.user_id, job.uuid, "deletion_warning"
            ):
                continue

            log.info(
                f"Sending transcription deletion warning notification to user {user.user_id} for job {job.uuid}."
            )

            # Send the notification
            notifications.send_job_to_be_deleted(user.email)
            notifications.notification_sent_record_add(
                user.user_id, job.uuid, "deletion_warning"
            )

    user_purge_deleted()


async def job_result_get(
    user_id: str,
    job_id: str,
) -> Optional[JobResult]:
    """
    Get the transcription result for a job by UUID.

    Parameters:
        user_id (str): The ID of the user requesting the job result.
        job_id (str): The UUID of the job.

    Returns:
        dict: The job result as a dictionary if found, otherwise an empty dictionary.
    """

    async with get_async_session() as session:
        result = await session.execute(
            select(JobResult).where(
                JobResult.job_id == job_id,
                JobResult.user_id == user_id,
            )
        )
        res = result.scalars().first()

        log.info(f"Job result for job {job_id} retrieved for user {user_id}.")

        return res.as_dict() if res else {}


async def job_result_get_external(
    external_id: str,
) -> Optional[JobResult]:
    """
    Get the transcription result for a job by UUID.

    Parameters:
        external_id (str): The external ID of the job.

    Returns:
        dict: The job result as a dictionary if found, otherwise an empty dictionary.
    """

    async with get_async_session() as session:
        result = await session.execute(
            select(JobResult).where(
                JobResult.external_id == external_id,
            )
        )
        res = result.scalars().first()

        return res.as_dict() if res else {}


async def job_result_save(
    uuid: str,
    user_id: str,
    result_srt: Optional[str] = {},
    result: Optional[str] = "",
    external_id: Optional[str] = None,
    result_path: Optional[str] = None,
) -> JobResult:
    """
    Save the transcription result for a job.

    Parameters:
        uuid (str): The UUID of the job.
        user_id (str): The ID of the user associated with the job.
        result_srt (str): The transcription result in SRT format.
        result (str): The transcription result in JSON format.
        external_id (str): An external ID associated with the job.
        result_path (str): The path to the result file.

    Returns:
        dict: The saved job result as a dictionary.

    Raises:
        ValueError: If the job is not found.
    """

    async with get_async_session() as session:
        job_check = await session.execute(
            select(Job).where(Job.uuid == uuid)
        )
        if not job_check.scalars().first():
            raise ValueError("Job not found")

        result_query = await session.execute(
            select(JobResult).where(
                JobResult.job_id == uuid,
                JobResult.user_id == user_id,
            )
        )
        job_result = result_query.scalars().first()

        if job_result:
            if result:
                job_result.result = result
            if result_srt:
                job_result.result_srt = result_srt
        else:
            job_result = JobResult(
                job_id=uuid,
                user_id=user_id,
                external_id=external_id,
                result=json.dumps(result) if result else None,
                result_srt=result_srt if result_srt else None,
                result_path=result_path if result_path else None,
            )

        session.add(job_result)

        log.info(f"Job result for job {uuid} saved for user {user_id}.")

        return job_result.as_dict()
