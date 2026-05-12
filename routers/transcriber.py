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

from fastapi import APIRouter, UploadFile, Request, Depends, Query, File
from fastapi.responses import JSONResponse
from db.job import (
    job_create,
    job_remove,
    job_get,
    job_get_all,
    job_update,
    job_result_get,
    job_result_save,
)
from db.models import JobType, JobStatusEnum, OutputFormatEnum
from db.user import (
    user_get_quota_left,
    user_get_private_key,
    user_get,
    user_get_public_key,
)
from typing import Optional
from utils.settings import get_settings
from pathlib import Path
from auth.oidc import get_current_user
from utils.crypto import (
    deserialize_public_key_from_pem,
    deserialize_private_key_from_pem,
    encrypt_string,
    decrypt_string,
    encrypt_stream_to_file,
)
from utils.log import get_logger
from utils.validators import TranscriptionStatusPut, TranscriptionResultPut

router = APIRouter(tags=["transcriber"])
settings = get_settings()

api_file_storage_dir = settings.API_FILE_STORAGE_DIR

logger = get_logger()


def decrypt_filename(job: dict, private_key) -> dict:
    """
    Try to decrypt the filename in a job dict, falling back to the raw value.
    """

    if not job.get("filename"):
        return job

    try:
        job["filename"] = decrypt_string(private_key, job["filename"])
    except Exception:
        pass

    return job


@router.get("/transcriber")
async def transcribe(
    request: Request,
    job_id: Optional[str] = Query(None, description="The ID of the job to get"),
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Transcribe audio file.

    Used by the frontend to get the status of a transcription job.

    Parameters:
        request (Request): The incoming HTTP request.
        job_id (str): The ID of the job to get. If empty, get all jobs for the user.
        status (Optional[JobStatus]): Filter jobs by status.
        user (dict): The current user.

    Returns:
        JSONResponse: The job status or list of jobs.
    """

    if job_id:
        res = await job_get(job_id, user["user_id"])
    else:
        res = await job_get_all(user["user_id"])

    # Try to decrypt filenames
    try:
        data = await request.json()
        encryption_password = data.get("encryption_password", "")
    except Exception:
        encryption_password = ""

    private_key = None

    if encryption_password:
        try:
            raw_private_key = await user_get_private_key(user["user_id"])
            private_key = deserialize_private_key_from_pem(
                raw_private_key, encryption_password
            )
        except Exception:
            private_key = None

    if private_key:
        if isinstance(res, dict) and "jobs" in res:
            res["jobs"] = [decrypt_filename(job, private_key) for job in res["jobs"]]
        elif isinstance(res, dict) and "uuid" in res:
            res = decrypt_filename(res, private_key)

    return JSONResponse(content={"result": res})


@router.post("/transcriber")
async def transcribe_file(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Transcribe audio file.

    Used by the frontend to upload an audio file for transcription.

    Parameters:
        request (Request): The incoming HTTP request.
        file (UploadFile): The uploaded audio file.
        user (dict): The current user.

    Returns:
        JSONResponse: The job status.
    """

    user_public_key = await user_get_public_key(user["user_id"])
    user_public_key = deserialize_public_key_from_pem(user_public_key)

    job = await job_create(
        user_id=user["user_id"],
        job_type=JobType.TRANSCRIPTION,
        filename=encrypt_string(user_public_key, file.filename),
    )

    if not (api_user := await user_get(username="api_user")):
        return JSONResponse(
            content={"result": {"error": "API user not found"}}, status_code=500
        )

    public_key = await user_get_public_key(api_user["user_id"])
    public_key = deserialize_public_key_from_pem(public_key)

    try:
        file_path = Path(api_file_storage_dir + "/" + user["user_id"])
        dest_path = file_path / job["uuid"]

        if not file_path.exists():
            file_path.mkdir(parents=True, exist_ok=True)

        await encrypt_stream_to_file(
            public_key,
            file,
            str(dest_path),
            chunk_size=settings.CRYPTO_CHUNK_SIZE,
        )

        job = await job_update(job["uuid"], status=JobStatusEnum.UPLOADED)
    except Exception as e:
        job = await job_update(
            job["uuid"], user["user_id"], status=JobStatusEnum.FAILED, error=str(e)
        )
        return JSONResponse(content={"result": {"error": str(e)}}, status_code=500)

    return JSONResponse(
        content={
            "result": {
                "uuid": job["uuid"],
                "user_id": user["user_id"],
                "status": job["status"],
                "job_type": job["job_type"],
                "filename": file.filename,
            }
        }
    )


@router.delete("/transcriber/{job_id}")
async def delete_transcription_job(
    request: Request,
    job_id: str,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Delete a transcription job.

    Used by the frontend to delete a transcription job.

    Parameters:
        request (Request): The incoming HTTP request.
        job_id (str): The ID of the job to delete.
        user (dict): The current user.

    Returns:
        JSONResponse: The result of the deletion.
    """

    if not await job_get(job_id, user["user_id"]):
        return JSONResponse(
            content={"result": {"error": "Job not found"}}, status_code=404
        )

    # Delete the job from the database
    await job_remove(job_id)

    # Remove the video file if it exists
    file_path = Path(api_file_storage_dir) / user["user_id"] / f"{job_id}.mp4"
    file_path_enc = Path(api_file_storage_dir) / user["user_id"] / f"{job_id}.mp4.enc"

    if file_path.exists():
        file_path.unlink()

    if file_path_enc.exists():
        file_path_enc.unlink()

    return JSONResponse(content={"result": {"status": "OK"}})


@router.put("/transcriber/{job_id}")
async def update_transcription_status(
    request: Request,
    item: TranscriptionStatusPut,
    job_id: str,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Update the status of a transcription job.

    Used by the frontend and worker to update the status of a transcription job.

    Parameters:
        request (Request): The incoming HTTP request.
        job_id (str): The ID of the job to update.
        user (dict): The current user.

    Returns:
        JSONResponse: The updated job status.
    """

    quota_left = await user_get_quota_left(user["user_id"])

    if not quota_left:
        logger.warning(f"Quota exceeded for user {user['user_id']}")
        return JSONResponse(
            content={
                "result": {
                    "error": "Quota exceeded, please contact your administrator."
                }
            },
            status_code=403,
        )

    if not (
        job := await job_update(
            job_id,
            user_id=user["user_id"],
            language=item.language,
            model_type="Slower transcription (higher accuracy)",
            speakers=item.speakers,
            status="pending",
            output_format=item.output_format,
            error=None,
        )
    ):
        return JSONResponse(
            content={"result": {"error": "Job not found"}}, status_code=404
        )

    # Try to decrypt the filename for the response
    filename = job["filename"]

    try:
        raw_private_key = await user_get_private_key(user["user_id"])
        if item.encryption_password:
            deserialized_key = deserialize_private_key_from_pem(
                raw_private_key, item.encryption_password
            )
            filename = decrypt_string(deserialized_key, filename)
    except Exception:
        pass

    return JSONResponse(
        content={
            "result": {
                "uuid": job["uuid"],
                "user_id": user["user_id"],
                "status": job["status"],
                "job_type": job["job_type"],
                "filename": filename,
                "language": job["language"],
                "model_type": job["model_type"],
                "output_format": job["output_format"],
            }
        }
    )


@router.put("/transcriber/{job_id}/result")
async def put_transcription_result(
    request: Request,
    item: TranscriptionResultPut,
    job_id: str,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Upload the transcription result.

    Parameters:
        request (Request): The incoming HTTP request.
        job_id (str): The ID of the job.
        user (dict): The current user.

    Returns:
        JSONResponse: The result of the upload.
    """
    try:
        if not await job_get(job_id, user["user_id"]):
            return JSONResponse(
                content={"result": {"error": "Job not found"}}, status_code=404
            )

        public_key = await user_get_public_key(user["user_id"])
        public_key = deserialize_public_key_from_pem(public_key)

        match item.format:
            case "srt":
                await job_result_save(
                    job_id,
                    user["user_id"],
                    result_srt=encrypt_string(public_key, item.data),
                )
            case "json":
                await job_result_save(
                    job_id,
                    user["user_id"],
                    result=encrypt_string(public_key, item.data),
                )
    except Exception as e:
        logger.error(f"Error saving transcription result for job {job_id}: {e}")
        return JSONResponse(content={"result": {"error": str(e)}}, status_code=500)

    return JSONResponse(content={"result": {"status": "OK"}}, status_code=200)


@router.get("/transcriber/{job_id}/result/{output_format}")
async def get_transcription_result(
    request: Request,
    job_id: str,
    output_format: OutputFormatEnum,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Get the transcription result.

    Parameters:
        request (Request): The incoming HTTP request.
        job_id (str): The ID of the job.
        output_format (OutputFormatEnum): The desired output format.
        user (dict): The current user.

    Returns:
        JSONResponse: The transcription result.
    """

    data = await request.json()
    encryption_password = data.get("encryption_password", "")
    private_key = await user_get_private_key(user["user_id"])

    if encryption_password == "":
        encrypted_result = False

    if not (job_result := await job_result_get(user["user_id"], job_id)):
        return JSONResponse(
            content={"result": {"error": "Job result not found"}}, status_code=404
        )

    if encryption_password != "" and encryption_password is not None:
        encrypted_result = True

        try:
            deserialized_private_key = deserialize_private_key_from_pem(
                private_key, encryption_password
            )
        except Exception:
            encrypted_result = False
    else:
        encrypted_result = False

    match output_format:
        case OutputFormatEnum.TXT:
            content = job_result.get("result", "")

            if encrypted_result:
                try:
                    content = decrypt_string(deserialized_private_key, content)
                except ValueError:
                    content = job_result.get("result", "")
        case OutputFormatEnum.SRT:
            content = job_result.get("result_srt", "")

            if encrypted_result:
                try:
                    content = decrypt_string(deserialized_private_key, content)
                except ValueError:
                    content = job_result.get("result_srt", "")
        case OutputFormatEnum.CSV:
            pass
        case _:
            return JSONResponse(
                content={"result": {"error": "Unsupported output format"}},
                status_code=400,
            )

    return JSONResponse(
        content={"result": content},
        media_type="text/plain",
    )
