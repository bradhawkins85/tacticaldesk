from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import get_settings
from app.schemas import MCPExecutionRequest, MCPExecutionResponse, MCPResourceDescriptor
from app.services.chatgpt_mcp import MCPConnectorError, connector

router = APIRouter(prefix="/api/mcp", tags=["ChatGPT MCP"])


async def _require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    settings = get_settings()
    expected_key = settings.mcp_api_key
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MCP connector is not configured",
        )
    if not secrets.compare_digest(x_api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


@router.get("/resources", response_model=list[MCPResourceDescriptor])
async def list_resources(_: None = Depends(_require_api_key)) -> list[MCPResourceDescriptor]:
    return await connector.list_resources()


@router.get("/resources/{slug}", response_model=MCPResourceDescriptor)
async def get_resource_descriptor(
    slug: str, _: None = Depends(_require_api_key)
) -> MCPResourceDescriptor:
    try:
        return await connector.get_resource_descriptor(slug)
    except MCPConnectorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/execute", response_model=MCPExecutionResponse)
async def execute_request(
    payload: MCPExecutionRequest, _: None = Depends(_require_api_key)
) -> MCPExecutionResponse:
    try:
        return await connector.execute(payload)
    except MCPConnectorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
