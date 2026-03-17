from typing import Any
import json
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.graph.builder import create_graph
from fileUpload.extract_content import extract_content

try:
    from langfuse.langchain import CallbackHandler
except Exception:
    CallbackHandler = None


app = FastAPI(title="AI2.0 API", version="1.0.0")
graph = create_graph()


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., description="用户输入")
    recursion_limit: int = Field(50, ge=1, le=200)


class ChatResponse(BaseModel):
    session_id: str
    final_message: str
    events: list[dict[str, Any]]


class UploadResponse(BaseModel):
    session_id: str
    file_name: str
    saved_path: str
    content_preview: str
    message: str = "文件上传和提取成功"


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
        # 1. 确保 session 目录存在
        session_dir = Path(f"./sessions/{session_id}")
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. 使用临时文件处理上传的文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        try:
            # 3. 提取文件内容
            extracted_content = extract_content(tmp_path)
            
            # 4. 生成输出文件名并保存
            file_stem = Path(file.filename).stem  # 获取文件名（不含扩展名）
            output_file = session_dir / f"{file_stem}.md"
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(extracted_content)
            
            # 5. 生成预览内容（前 500 字符）
            preview = extracted_content[:500] + ("..." if len(extracted_content) > 500 else "")
            
            return UploadResponse(
                session_id=session_id,
                file_name=file.filename,
                saved_path=str(output_file),
                content_preview=preview,
                message="文件上传和提取成功"
            )
        
        finally:
            # 清理临时文件
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    except Exception as e:
        return UploadResponse(
            session_id=session_id,
            file_name=file.filename,
            saved_path="",
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
