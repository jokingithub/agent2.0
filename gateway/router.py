# -*- coding: utf-8 -*-
import json

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, Query
from fastapi.responses import JSONResponse, StreamingResponse, Response

from app.Schema import ChatRequest
from gateway.auth import require_token
from gateway.schemas import (
    ToolInvokeRequest,
    FileInfo,
    FileProcessingStatus,
)
from gateway.store import GatewayConfigStore
from typing import Any, Dict, List

router = APIRouter(prefix="/gateway", tags=["gateway"])
protected_router = APIRouter(
    prefix="/gateway",
    tags=["gateway"],
    dependencies=[Depends(require_token)],
)
store = GatewayConfigStore()


def _is_local_ip(ip: str) -> bool:
    return ip in {"127.0.0.1", "::1", "localhost"}


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/backend")
def current_backend() -> dict[str, str]:
    return {"backend_base_url": store.get_backend_base_url()}


@router.post("/tool/invoke")
async def invoke_tool(
    request: Request,
    req: ToolInvokeRequest,
):
    client_ip = (request.client.host if request.client else "")
    if not _is_local_ip(client_ip):
        raise HTTPException(status_code=403, detail="工具调用仅允许本地IP访问")

    tool = store.get_tool(req.tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"tool 不存在: {req.tool_id}")

    if str(tool.get("enabled", "true")).lower() != "true":
        raise HTTPException(status_code=403, detail=f"tool 已禁用: {req.tool_id}")

    backend = store.get_backend_base_url()
    try:
        target_url, method, extra_headers, _, timeout_sec = store.build_tool_target(tool, backend)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    headers: dict[str, str] = {"Content-Type": "application/json"}
    headers.update({k: str(v) for k, v in extra_headers.items()})

    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        resp = await client.request(
            method=method,
            url=target_url,
            headers=headers,
            json=req.params,
        )

    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type.lower():
        return JSONResponse(status_code=resp.status_code, content=resp.json())

    return JSONResponse(
        status_code=resp.status_code,
        content={"raw": resp.text},
    )


@protected_router.post("/upload")
async def gateway_upload(
    session_id: str = Form(...),
    app_id: str = Form(..., min_length=1),
    file: UploadFile = File(...),
):
    backend = store.get_backend_base_url()
    target_url = f"{backend}/upload"

    content = await file.read()
    files = {
        "file": (
            file.filename,
            content,
            file.content_type or "application/octet-stream",
        )
    }
    data = {
        "session_id": session_id,
        "app_id": app_id,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(target_url, data=data, files=files)

    return JSONResponse(status_code=resp.status_code, content=resp.json())


@protected_router.post("/chat")
async def gateway_chat(
    req: ChatRequest,
):
    backend = store.get_backend_base_url()
    target_url = f"{backend}/chat"

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(target_url, json=req.model_dump())

    return JSONResponse(status_code=resp.status_code, content=resp.json())


@protected_router.post("/chat/stream")
async def gateway_chat_stream(
    req: ChatRequest,
):
    backend = store.get_backend_base_url()
    target_url = f"{backend}/chat/stream"

    async def stream_gen():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", target_url, json=req.model_dump()) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    payload = {
                        "status": resp.status_code,
                        "detail": body.decode("utf-8", errors="ignore"),
                    }
                    yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    return

                async for chunk in resp.aiter_text():
                    yield chunk

    return StreamingResponse(stream_gen(), media_type="text/event-stream")


@protected_router.get("/sessions/{session_id}/hitl/status")
async def gateway_hitl_status(
    session_id: str,
    app_id: str = Query(..., min_length=1, description="应用ID"),
):
    backend = store.get_backend_base_url()
    target_url = f"{backend}/sessions/{session_id}/hitl/status"

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(target_url, params={"app_id": app_id})

    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type.lower():
        return JSONResponse(status_code=resp.status_code, content=resp.json())

    return JSONResponse(status_code=resp.status_code, content={"raw": resp.text})


@protected_router.post("/sessions/{session_id}/hitl/resume")
async def gateway_hitl_resume(
    session_id: str,
    request: Request,
):
    backend = store.get_backend_base_url()
    target_url = f"{backend}/sessions/{session_id}/hitl/resume"
    body = await request.json()

    async def stream_gen():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", target_url, json=body) as resp:
                if resp.status_code >= 400:
                    raw = await resp.aread()
                    payload = {
                        "status": resp.status_code,
                        "detail": raw.decode("utf-8", errors="ignore"),
                    }
                    yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    return

                async for chunk in resp.aiter_text():
                    yield chunk

    return StreamingResponse(stream_gen(), media_type="text/event-stream")

@protected_router.get("/file_content",response_model=FileInfo)
async def gateway_file(
    session_id: str = Query(...),
    app_id: str = Query(..., min_length=1),
    file_id: str = Query(...),
):
    backend = store.get_backend_base_url()
    target_url = f"{backend}/files/{file_id}/content"

    # GET 请求参数应该放在 params 中（URL 参数）
    params = {
        "app_id": app_id,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.get(target_url, params=params)
            
            # 检查后端是否返回错误
            if resp.status_code != 200:
                return JSONResponse(status_code=resp.status_code, content=resp.json())

            # 如果返回的是文件内容，直接透传 content 和 media_type
            return Response(
                content=resp.content, 
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type")
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@protected_router.get("/files/{file_id}/status", response_model=FileProcessingStatus)
async def gateway_file_processing_status(
    file_id: str,
    app_id: str = Query(..., min_length=1, description="应用ID"),
):
    backend = store.get_backend_base_url()
    target_url = f"{backend}/files/{file_id}/status"
    params = {"app_id": app_id}

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.get(target_url, params=params)

            if resp.status_code != 200:
                try:
                    error_detail = resp.json()
                except Exception:
                    error_detail = {"detail": resp.text}
                return JSONResponse(status_code=resp.status_code, content=error_detail)

            return resp.json()

        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Backend service unreachable: {str(exc)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@protected_router.get("/files/{file_id}/download")
async def gateway_download_file(
    file_id: str,
    app_id: str = Query(..., min_length=1, description="应用ID"),
):
    backend = store.get_backend_base_url()
    target_url = f"{backend}/files/{file_id}/download"
    params = {"app_id": app_id}

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.get(target_url, params=params)

            if resp.status_code != 200:
                content_type = resp.headers.get("content-type", "")
                if "application/json" in content_type.lower():
                    return JSONResponse(status_code=resp.status_code, content=resp.json())
                return JSONResponse(status_code=resp.status_code, content={"detail": resp.text})

            headers: dict[str, str] = {}
            content_disposition = resp.headers.get("content-disposition")
            if content_disposition:
                headers["content-disposition"] = content_disposition

            media_type = resp.headers.get("content-type") or "application/octet-stream"
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=media_type,
                headers=headers,
            )

        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Backend service unreachable: {str(exc)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        
@protected_router.get("/file_list", response_model=List[FileInfo])
async def gateway_file_list(
    session_id: str = Query(..., description="会话ID"),
    app_id: str = Query(..., min_length=1, description="应用ID")
):
    backend_base = store.get_backend_base_url()
    # 按照后端接口规范拼接 URL
    target_url = f"{backend_base}/sessions/{session_id}/files"
    
    query_params = {"app_id": app_id}

    # 建议：在生产环境中，应使用全局单例的 httpx.AsyncClient()
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.get(target_url, params=query_params)
            
            # 检查非 200 状态码
            if resp.status_code != 200:
                # 尝试解析错误 JSON，解析失败则返回原始文本
                try:
                    error_detail = resp.json()
                except:
                    error_detail = resp.text
                return JSONResponse(status_code=resp.status_code, content=error_detail)

            # 成功直接解析 JSON 并返回（FastAPI 会根据 response_model 自动校验）
            return resp.json()

        except httpx.RequestError as exc:
            # 捕获网络层错误（如连接超时、DNS 失败）
            raise HTTPException(status_code=503, detail=f"Backend service unreachable: {str(exc)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@protected_router.delete("/sessions/{session_id}/files/{file_id}")
async def gateway_remove_file_from_session(
    session_id: str,
    file_id: str,
    app_id: str = Query("", description="应用ID"),
):
    backend_base = store.get_backend_base_url()
    target_url = f"{backend_base}/sessions/{session_id}/files/{file_id}"

    query_params = {"app_id": app_id}

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.delete(target_url, params=query_params)

            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type.lower():
                return JSONResponse(status_code=resp.status_code, content=resp.json())

            return JSONResponse(
                status_code=resp.status_code,
                content={"raw": resp.text},
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail=f"Backend service unreachable: {str(exc)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))