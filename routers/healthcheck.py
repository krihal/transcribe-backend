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

import time

from auth.client import verify_client_dn
from auth.oidc import get_current_admin_user
from db.session import get_async_session
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from utils.health import HealthStatus
from utils.log import get_logger

log = get_logger()
router = APIRouter(tags=["healthcheck"])
health = HealthStatus()


@router.post("/healthcheck", include_in_schema=False)
async def healthcheck(
    request: Request,
    client_dn: str = Depends(verify_client_dn),
) -> JSONResponse:
    """
    Recevice a JSON blob with system data from the GPU workers.

    Parameters:
        request (Request): The incoming HTTP request.

    Returns:
        JSONResponse: The result of the health check.
    """

    data = await request.json()

    health.add(data)

    return JSONResponse(content={"result": "ok"})


@router.get("/healthcheck", include_in_schema=False)
async def get_healthcheck(
    request: Request,
    admin_user: dict = Depends(get_current_admin_user),
) -> JSONResponse:
    """
    Get the health status of all workers.

    Parameters:
        request (Request): The incoming HTTP request.
        user_id (str): The ID of the user.

    Returns:
        JSONResponse: The health status of all workers.
    """

    if not admin_user["bofh"]:
        log.warning(f"Non-BOFH user {admin_user['user_id']} denied access to healthcheck")
        return JSONResponse(
            content={"error": "User not authorized"},
            status_code=403,
        )

    data = health.get()

    return JSONResponse(content={"result": data})


@router.get("/status", include_in_schema=False)
async def get_status() -> JSONResponse:
    """
    Status endpoint to check if backend, database, and workers are working.
    Not exposed in API documentation.

    Returns:
        JSONResponse: Status of backend, database, and worker connectivity.
    """

    status = {
        "backend": "ok",
        "database": "ok",
        "workers": "error",
        "workers_online": 0,
    }

    # Check database connectivity
    try:
        async with get_async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        status["database"] = "error"

    # Check worker status - worker is online if seen within last 2 minutes
    now = time.time()
    online_count = 0
    worker_data = health.get()

    workers_detail = {}
    for idx, (worker_id, stats) in enumerate(worker_data.items()):
        if stats:
            last_seen = stats[-1].get("seen", 0)
            if now - last_seen < 120:
                online_count += 1
                gpu = stats[-1].get("gpu_usage", 0)
                if isinstance(gpu, list):
                    gpu = max((g.get("utilization", 0) for g in gpu if isinstance(g, dict)), default=0)
                elif isinstance(gpu, dict):
                    gpu = gpu.get("utilization", 0)
                workers_detail[f"worker-{idx}"] = {"busy": gpu > 0}

    status["workers_online"] = online_count
    status["workers_detail"] = workers_detail
    if online_count > 0:
        status["workers"] = "ok"

    # Determine overall status (workers not critical for basic health)
    core_ok = status["backend"] == "ok" and status["database"] == "ok"
    status_code = 200 if core_ok else 503

    return JSONResponse(content=status, status_code=status_code)
