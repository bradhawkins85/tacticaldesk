from __future__ import annotations

import asyncio
from asyncio.subprocess import PIPE
from pathlib import Path
from typing import Any
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import get_settings

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _compare_tokens(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def require_maintenance_token(
    x_maintenance_token: str | None = Header(default=None, alias="X-Maintenance-Token"),
) -> None:
    settings = get_settings()
    if not settings.maintenance_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Maintenance token not configured",
        )
    if not x_maintenance_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Maintenance token required",
        )
    if not _compare_tokens(x_maintenance_token, settings.maintenance_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid maintenance token",
        )


async def _run_script(script_name: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.enable_installers:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Installer execution is disabled on this node",
        )

    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")

    process = await asyncio.create_subprocess_exec(
        "/bin/bash",
        str(script_path),
        stdout=PIPE,
        stderr=PIPE,
    )
    stdout, stderr = await process.communicate()
    result = {
        "return_code": process.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }
    if process.returncode != 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result)
    return result


@router.get("/scripts")
async def list_scripts() -> dict[str, Any]:
    available = [
        {
            "name": "Production install",
            "slug": "install",
            "description": "Initial provisioning of the Tactical Desk production environment.",
        },
        {
            "name": "Production update",
            "slug": "update",
            "description": "Pull the latest code, update dependencies, and restart the service.",
        },
        {
            "name": "Development install",
            "slug": "install-dev",
            "description": "Provision an isolated development environment backed by a separate database.",
        },
    ]
    return {"scripts": available, "enabled": get_settings().enable_installers}


@router.post("/install")
async def trigger_install(_: None = Depends(require_maintenance_token)) -> dict[str, Any]:
    result = await _run_script("install.sh")
    return {"status": "completed", "result": result}


@router.post("/update")
async def trigger_update(_: None = Depends(require_maintenance_token)) -> dict[str, Any]:
    result = await _run_script("update.sh")
    return {"status": "completed", "result": result}


@router.post("/install-dev")
async def trigger_dev_install(_: None = Depends(require_maintenance_token)) -> dict[str, Any]:
    result = await _run_script("install_dev.sh")
    return {"status": "completed", "result": result}
