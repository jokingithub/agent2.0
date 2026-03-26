# -*- coding: utf-8 -*-
# 文件：app/api.py

import json
import os
import asyncio
from typing import Any, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from langchain_core.callbacks import BaseCallbackHandler

from app.graph.builder import create_graph
from app.Schema import ChatRequest, ChatResponse, UploadResponse
from fileUpload.fileUpload import save_file
from logger import logger
from config import Config
from app.config_api import router as config_router
from dataBase.ConfigService import ChatLogService
from dataBase.Service import SessionService

try:
    from langfuse.langchain import CallbackHandler
except Exception:
    CallbackHandler = None

_docs_url = "/docs" if Config.ENABLE_API_DOCS else None
_redoc_url = "/redoc" if Config.ENABLE_API_DOCS else None
_openapi_url = "/openapi.json" if Config.ENABLE_API_DOCS else None

app = FastAPI(
    title="AI2.0 API",
    version="1.0.0",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)
app.include_router(config_router)
graph = create_graph()


# ============================================================
# Token & 耗时 收集器
# ============================================================

class UsageCollector(BaseCallbackHandler):
    """
    收集每次 LLM 调用的 token + 模型 + agent(node)
    """
    def __init__(self):
        super().__init__()
        self.total_tokens: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.first_token_time: Optional[datetime] = None

        self.call_details: list[dict[str, Any]] = []
        self._seq: int = 0
        self._current_model: str = "unknown"
        self._current_agent: str = "unknown"

    def on_llm_start(self, serialized, prompts=None, *, invocation_params=None, **kwargs):
        if self.first_token_time is None:
            self.first_token_time = datetime.now(timezone.utc)

        self._seq += 1

        # 1) model 名
        model_name = None
        if invocation_params:
            model_name = invocation_params.get("model") or invocation_params.get("model_name")
        if not model_name and serialized:
            kw = serialized.get("kwargs", {}) if isinstance(serialized, dict) else {}
            model_name = kw.get("model") or kw.get("model_name")
        self._current_model = model_name or "unknown"

        # 2) agent 名（LangGraph 注入）
        metadata = kwargs.get("metadata", {}) or {}
        self._current_agent = metadata.get("langgraph_node", "unknown")

    def on_llm_end(self, response, **kwargs):
        call_prompt = 0
        call_completion = 0
        call_total = 0

        # 优先 llm_output
        try:
            if response and hasattr(response, "llm_output") and response.llm_output:
                usage = response.llm_output.get("token_usage") or response.llm_output.get("usage") or {}
                call_total = usage.get("total_tokens", 0) or 0
                call_prompt = usage.get("prompt_tokens", 0) or 0
                call_completion = usage.get("completion_tokens", 0) or 0
        except Exception:
            pass

        # 兜底 generations
        if call_total == 0:
            try:
                if response and hasattr(response, "generations"):
                    for gen_list in response.generations:
                        for gen in gen_list:
                            info = getattr(gen, "generation_info", None) or {}
                            usage = info.get("token_usage") or info.get("usage") or {}
                            call_total += usage.get("total_tokens", 0) or 0
                            call_prompt += usage.get("prompt_tokens", 0) or 0
                            call_completion += usage.get("completion_tokens", 0) or 0
            except Exception:
                pass

        self.total_tokens += call_total
        self.prompt_tokens += call_prompt
        self.completion_tokens += call_completion

        self.call_details.append({
            "seq": self._seq,
            "agent": self._current_agent,   # 你要的字段
            "model": self._current_model,
            "prompt_tokens": call_prompt,
            "completion_tokens": call_completion,
            "total_tokens": call_total,
        })

    @property
    def final_model(self) -> Optional[str]:
        if not self.call_details:
            return None
        return self.call_details[-1].get("model")

    @property
    def final_agent(self) -> Optional[str]:
        if not self.call_details:
            return None
        return self.call_details[-1].get("agent")


# ============================================================
# 路由
# ============================================================

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
async def upload_file(
    session_id: str = Form(..., description="会话 ID"),
    app_id: str = Form("", description="应用 ID"),
    file: UploadFile = File(..., description="上传的文件")
) -> UploadResponse:
    try:
        result = await save_file(file, session_id, app_id=app_id)
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


# ============================================================
# 日志写入
# ============================================================

async def _save_chat_log(
    app_id: str,
    scene_id: str,
    session_id: str,
    request_content: str,
    response_content: str,
    request_time: datetime,
    collector: UsageCollector,
):
    """异步保存会话日志 + 对话记忆"""
    end_time = datetime.now(timezone.utc)

    # 写 memories（assistant 消息带模型名）
    try:
        session_service = SessionService()
        session_service.append_chat_message(session_id, "user", request_content, app_id=app_id)
        if response_content:
            session_service.append_chat_message(
                session_id, "assistant", response_content,
                app_id=app_id,
                model_name=collector.final_model or "",
                agent_name=collector.final_agent or "",   # 新增
            )
        logger.info(f"会话记忆已保存: session={session_id}")
    except Exception as e:
        logger.error(f"保存会话记忆失败: {e}", exc_info=True)

    # 写 chat_logs
    try:
        log_service = ChatLogService()
        log_data = {
            "app_id": app_id,
            "scene_id": scene_id,
            "session_id": session_id,
            "request_content": request_content,
            "response_content": response_content,
            "request_time": request_time.isoformat(),
            "first_token_time": collector.first_token_time.isoformat() if collector.first_token_time else None,
            "end_time": end_time.isoformat(),
            "total_tokens": collector.total_tokens or None,
            "prompt_tokens": collector.prompt_tokens or None,
            "completion_tokens": collector.completion_tokens or None,
            # ===== 新增：模型追踪 =====
            "model_detail": collector.call_details if collector.call_details else None,
            "final_model": collector.final_model,
        }
        await log_service.save_log_async(log_data)
        logger.info(
            f"会话日志已保存: session={session_id}, "
            f"tokens={collector.total_tokens}, "
            f"models={[d['model'] for d in collector.call_details]}"  # 日志里也打出来
        )
    except Exception as e:
        logger.error(f"保存会话日志失败: {e}", exc_info=True)



# ============================================================
# /chat — 非流式
# ============================================================

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    request_time = datetime.now(timezone.utc)
    app_id = req.app_id or ""

    collector = UsageCollector()
    callbacks = [collector]

    session_service = SessionService()
    session_service.ensure_session(req.session_id, app_id=app_id)

    history = session_service.memory_service.get_recent_messages(
        req.session_id, last_n=20, app_id=app_id
    )

    messages = [(msg["role"], msg["content"]) for msg in history]
    messages.append(("user", req.message))

    inputs = {
        "session_id": req.session_id,
        "app_id": app_id,
        "messages": messages,
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
            node_messages = node_value.get("messages") if isinstance(node_value, dict) else None
            if node_messages:
                last = node_messages[-1]
                content = getattr(last, "content", "")
                event["message"] = content
                if isinstance(content, str) and content.strip():
                    final_message = content
            events.append(event)

    asyncio.create_task(_save_chat_log(
        app_id=app_id,
        scene_id=req.scene_id,
        session_id=req.session_id,
        request_content=req.message,
        response_content=final_message,
        request_time=request_time,
        collector=collector,
    ))

    session_service.touch_session(req.session_id, app_id=app_id)

    return ChatResponse(
        session_id=req.session_id,
        final_message=final_message,
        events=events,
    )


# ============================================================
# /chat/stream — 流式
# ============================================================

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    request_time = datetime.now(timezone.utc)
    app_id = req.app_id or ""

    collector = UsageCollector()
    callbacks = [collector]

    session_service = SessionService()
    session_service.ensure_session(req.session_id, app_id=app_id)

    history = session_service.memory_service.get_recent_messages(
        req.session_id, last_n=20, app_id=app_id
    )

    messages = [(msg["role"], msg["content"]) for msg in history]
    messages.append(("user", req.message))

    inputs = {
        "session_id": req.session_id,
        "app_id": app_id,
        "messages": messages,
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
                node_messages = node_value.get("messages") if isinstance(node_value, dict) else None
                if node_messages:
                    last = node_messages[-1]
                    content = getattr(last, "content", "")
                    payload["message"] = content
                    if isinstance(content, str) and content.strip():
                        final_message = content
                yield f"event: node\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        # 流结束后写日志
        asyncio.create_task(_save_chat_log(
            app_id=app_id,
            scene_id=req.scene_id,
            session_id=req.session_id,
            request_content=req.message,
            response_content=final_message,
            request_time=request_time,
            collector=collector,
        ))

        session_service.touch_session(req.session_id, app_id=app_id)

        done_payload = {
            "session_id": req.session_id,
            "final_message": final_message,
        }
        yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
