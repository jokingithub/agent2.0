# -*- coding: utf-8 -*-
# 文件：app/api.py
# time: 2026/3/10

from typing import Any
import json
import asyncio
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import StreamingResponse

from app.graph.builder import create_graph
from app.Schema import ChatRequest, ChatResponse, UploadResponse
from fileUpload.fileUpload import save_file
from logger import logger
from app.config_api import router as config_router
from dataBase.ConfigService import ChatLogService

try:
    from langfuse.langchain import CallbackHandler
except Exception:
    CallbackHandler = None

app = FastAPI(title="AI2.0 API", version="1.0.0")
app.include_router(config_router)
graph = create_graph()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
async def upload_file(
    session_id: str = Form(..., description="会话 ID"),
    file: UploadFile = File(..., description="上传的文件")
) -> UploadResponse:
    try:
        result = await save_file(file, session_id)
        return UploadResponse(**result)
    except Exception as e:
        logger.error(f"文件处理失败: {str(e)}", exc_info=False)
        return UploadResponse(
            session_id=session_id,
            file_name=file.filename,
            file_id="",
            file_type=[],
            content_preview="",
            message=f"文件处理失败: {str(e)}"
        )


def _extract_langfuse_trace_id(callbacks: list) -> str:
    """从 Langfuse 回调中提取 trace_id"""
    if not callbacks:
        return ""
    try:
        handler = callbacks[0]
        if hasattr(handler, "get_trace_id"):
            return handler.get_trace_id() or ""
        if hasattr(handler, "trace") and handler.trace:
            return getattr(handler.trace, "id", "") or ""
        if hasattr(handler, "trace_id"):
            return handler.trace_id or ""
    except Exception:
        pass
    return ""


async def _save_chat_log(
    app_id: str,
    scene_id: str,
    session_id: str,
    request_content: str,
    response_content: str,
    request_time: datetime,
    langfuse_trace_id: str = "",
):
    """异步保存会话日志（业务维度），技术细节交给 Langfuse"""
    try:
        log_service = ChatLogService()
        log_data = {
            "app_id": app_id,
            "scene_id": scene_id,
            "session_id": session_id,
            "request_content": request_content,
            "response_content": response_content,
            "langfuse_trace_id": langfuse_trace_id,
            "request_time": request_time.isoformat(),
        }
        await log_service.save_log_async(log_data)
        logger.info(f"会话日志已保存: session={session_id}, trace={langfuse_trace_id}")
    except Exception as e:
        logger.error(f"保存会话日志失败: {e}", exc_info=True)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    request_time = datetime.now()

    callbacks = []
    if CallbackHandler is not None:
        callbacks.append(CallbackHandler())

    inputs = {
        "session_id": req.session_id,
        "messages": [("user", req.message)],
    }

    events: list[dict[str, Any]] = []
    final_message = ""

    async for output in graph.astream(
        inputs,
        config={
            "recursion_limit": req.recursion_limit,
            "configurable": {"thread_id": req.session_id},
            "callbacks": callbacks,
        },
    ):
        for node_name, node_value in output.items():
            event: dict[str, Any] = {"node": node_name}
            messages = node_value.get("messages") if isinstance(node_value, dict) else None
            if messages:
                last = messages[-1]
                content = getattr(last, "content", "")
                event["message"] = content
                if isinstance(content, str) and content.strip():
                    final_message = content
            events.append(event)

    # 提取 Langfuse trace_id，异步写入业务日志
    trace_id = _extract_langfuse_trace_id(callbacks)
    asyncio.create_task(_save_chat_log(
        app_id=req.app_id,
        scene_id=req.scene_id,
        session_id=req.session_id,
        request_content=req.message,
        response_content=final_message,
        request_time=request_time,
        langfuse_trace_id=trace_id,
    ))

    return ChatResponse(
        session_id=req.session_id,
        final_message=final_message,
        events=events,
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    request_time = datetime.now()

    callbacks = []
    if CallbackHandler is not None:
        callbacks.append(CallbackHandler())

    inputs = {
        "session_id": req.session_id,
        "messages": [("user", req.message)],
    }

    async def event_gen():
        final_message = ""

        async for output in graph.astream(
            inputs,
            config={
                "recursion_limit": req.recursion_limit,
                "configurable": {"thread_id": req.session_id},
                "callbacks": callbacks,
            },
        ):
            for node_name, node_value in output.items():
                payload: dict[str, Any] = {"node": node_name}
                messages = node_value.get("messages") if isinstance(node_value, dict) else None
                if messages:
                    last = messages[-1]
                    content = getattr(last, "content", "")
                    payload["message"] = content
                    if isinstance(content, str) and content.strip():
                        final_message = content
                yield f"event: node\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        # 流结束后异步写入业务日志
        trace_id = _extract_langfuse_trace_id(callbacks)
        asyncio.create_task(_save_chat_log(
            app_id=req.app_id,
            scene_id=req.scene_id,
            session_id=req.session_id,
            request_content=req.message,
            response_content=final_message,
            request_time=request_time,
            langfuse_trace_id=trace_id,
        ))

        done_payload = {
            "session_id": req.session_id,
            "final_message": final_message,
        }
        yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
