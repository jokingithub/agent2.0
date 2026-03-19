# -*- coding: utf-8 -*-
# 文件：app/api.py
# time: 2026/3/10

from typing import Any
import json
import os

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import StreamingResponse

from app.graph.builder import create_graph
from app.Schema import ChatRequest, ChatResponse, UploadResponse
from fileUpload.fileUpload import save_file
from logger import logger


try:
    from langfuse.langchain import CallbackHandler
except Exception:
    CallbackHandler = None

app = FastAPI(title="AI2.0 API", version="1.0.0")
graph = create_graph()

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
async def upload_file(
    session_id: str = Form(..., description="会话 ID"),
    file: UploadFile = File(..., description="上传的文件")
) -> UploadResponse:
    """
    上传文件并提取内容。
    支持的文件类型：PDF、DOCX、图片（JPG/PNG等）、文本文件
    """
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


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
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

    return ChatResponse(
        session_id=req.session_id,
        final_message=final_message,
        events=events,
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
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

        done_payload = {
            "session_id": req.session_id,
            "final_message": final_message,
        }
        yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
