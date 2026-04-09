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

import aiofiles
import httpx

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from db.job import (
    job_create,
    job_get_by_external_id,
    job_remove,
    job_update,
    job_result_get_external,
)
from db.models import JobStatus, JobType, JobStatusEnum
from db.user import user_create, user_get_public_key, user_get, user_get_private_key
from auth.client import verify_client_dn
from utils.log import get_logger
from utils.settings import get_settings
from utils.validators import TranscribeExternalPost
from utils.crypto import (
    encrypt_data_to_file,
    deserialize_public_key_from_pem,
    decrypt_string,
    deserialize_private_key_from_pem,
)


logger = get_logger()
router = APIRouter(tags=["external"])
settings = get_settings()
api_file_storage_dir = settings.API_FILE_STORAGE_DIR


@router.get("/transcriber/external/{external_id}", include_in_schema=False)
async def get_job_external(
    request: Request,
    external_id: str = "",
    status: Optional[JobStatus] = None,
    client_dn: str = Depends(verify_client_dn),
) -> JSONResponse:
    """
    Get job by external id.

    Used by external integrations.

    Parameters:
        request (Request): The incoming HTTP request.
        external_id (str): The external ID of the job.
        status (Optional[JobStatus]): Filter jobs by status.

    Returns:
        JSONResponse: The job status.
    """

    res = await job_get_by_external_id(external_id, client_dn)

    if not isinstance(res, dict) and res and res["status"] == "completed":
        logger.error(f"External job not found: {external_id}")
        return JSONResponse(
            content={
                "result": res
            },
        )

    if not (job_result := await job_result_get_external(external_id)):
        logger.warning(f"External job result not found: {external_id}")
        return JSONResponse(
            content={
                "result": res
            },
        )

    try:
        # Decrypt the result text
        user = await user_get(username="api_user")
        private_key = await user_get_private_key(user["user_id"])
        deserialized_private_key = deserialize_private_key_from_pem(
            private_key, settings.API_PRIVATE_KEY_PASSWORD
        )
    except Exception as e:
        logger.error(f"Error deserializing private key for external job result: {e}")
        return JSONResponse(
            content={
                "result": {"error": "Error processing job result"}
            },
            status_code=500,
        )

    job_result = decrypt_string(deserialized_private_key, job_result["result_srt"])

    res["result_srt"] = job_result

    logger.info(f"Returning external job result for: {external_id}")

    return JSONResponse(content={"result": res})

@router.delete("/transcriber/external/{external_id}", include_in_schema=False)
async def delete_external_transcription_job(
    request: Request,
    external_id: str,
    client_dn: str = Depends(verify_client_dn),
) -> JSONResponse:
    """
    Delete an external transcription job.
    Used by integrations to clean up completed/failed jobs.

    Parameters:
        request (Request): The incoming HTTP request.
        external_id (str): The external ID of the job to delete.

    Returns:
        JSONResponse: The result of the deletion.
    """
    job = await job_get_by_external_id(external_id, client_dn)

    if not job:
        return JSONResponse(
            content={"result": {"error": "Job not found"}}, status_code=404
        )

    # Delete the job from the database
    status = await job_remove(job["uuid"])

    if status is False:
        logger.debug(f"JOB REMOVE FALSE: {job}")

    # Remove the video file if it exists
    file_path = Path(api_file_storage_dir) / job["user_id"] / f"{job["uuid"]}.mp4"

    if file_path.exists():
        file_path.unlink()

    return JSONResponse(content={"result": {"status": "OK"}})


@router.post("/transcriber/external", include_in_schema=False)
async def transcribe_external_file(
    item: TranscribeExternalPost,
    request: Request,
    client_dn: str = Depends(verify_client_dn),
) -> JSONResponse:
    """
    Transcribe audio file.

    Used by external integrations to upload files.

    Parameters:
        request (Request): The incoming HTTP request.

    Returns:
        JSONResponse: The job status.

    Raise:
        Exception: If there is an error during processing.
    """

    filename = item.file_url.split("/")[-1]
    job = None

    try:
        async with httpx.AsyncClient() as client:
            kaltura_repsonse = await client.get(item.file_url, timeout=120)

        if kaltura_repsonse.status_code != 200:
            raise Exception(
                "Bad status code response from kaltura: {}".format(
                    kaltura_repsonse.status_code
                )
            )

        await user_create(username=item.user_id, user_id=item.user_id, realm="external")

        job = await job_create(
            user_id=item.user_id,
            job_type=JobType.TRANSCRIPTION,
            filename=filename,
            language=item.language,
            model_type="slower transcription (higher accuracy)",
            output_format=item.output_format,
            external_id=item.id,
            external_user_id=None,
            client_dn=client_dn,
        )

        file_path = Path(api_file_storage_dir + "/" + item.user_id)
        dest_path = file_path / job["uuid"]

        if not file_path.exists():
            file_path.mkdir(parents=True, exist_ok=True)

        if not (api_user := await user_get(username="api_user")):
            return JSONResponse(
                content={"result": {"error": "API user not found"}}, status_code=500
            )

        public_key = await user_get_public_key(api_user["user_id"])
        public_key = deserialize_public_key_from_pem(public_key)

        encrypt_data_to_file(
            public_key,
            kaltura_repsonse.content,
            dest_path,
            chunk_size=settings.CRYPTO_CHUNK_SIZE,
        )

    except Exception as e:
        logger.error("Caught exception while creating external job - {}".format(e))
        if job is not None:
            job = await job_update(
                job["uuid"], item.user_id, status=JobStatusEnum.FAILED, error=str(e)
            )
        return JSONResponse(content={"result": {"error": str(e)}}, status_code=500)

    job = await job_update(job["uuid"], status=JobStatusEnum.PENDING)

    return JSONResponse(
        content={
            "result": {
                "uuid": job["uuid"],
                "user_id": item.user_id,
                "status": job["status"],
                "job_type": job["job_type"],
                "filename": filename,
            }
        }
    )
