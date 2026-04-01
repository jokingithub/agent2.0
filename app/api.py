# -*- coding: utf-8 -*-
# 文件：app/api.py

import json
import os
import asyncio
from typing import Any, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage, ToolMessage

from app.graph.builder import create_graph
from app.Schema import ChatRequest, ChatResponse, UploadResponse, UsageCollector
from fileUpload.fileUpload import save_file
from logger import logger
from config import Config
from app.config_api import router as config_router
from app.session_api import router as session_router
from dataBase.ConfigService import ChatLogService
from dataBase.Service import SessionService
from fastapi.middleware.cors import CORSMiddleware
from app.file_api import router as file_router


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
app.include_router(session_router)
app.include_router(file_router)
graph = create_graph()


origins = [
    "http://localhost",
    "http://localhost:3000",
    "https://your-frontend-domain.com",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    session_service = SessionService()
    try:
        session_service.ensure_session(session_id, app_id=app_id)
        result = await save_file(file, session_id, app_id=app_id)
        session_service.touch_session(session_id, app_id=app_id)
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


class MCPDebugListRequest(BaseModel):
    url: str = Field(default="http://127.0.0.1:9001/sse", description="MCP SSE 地址")
    timeout_seconds: int = Field(default=20, ge=1, le=120, description="超时时间（秒）")


class MCPDebugCallRequest(BaseModel):
    url: str = Field(default="http://127.0.0.1:9001/sse", description="MCP SSE 地址")
    tool_name: str = Field(..., min_length=1, description="工具名")
    args: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    timeout_seconds: int = Field(default=30, ge=1, le=120, description="超时时间（秒）")


def _extract_mcp_result_text(result: Any) -> str:
    """尽量提取 MCP 返回中的文本内容。"""
    try:
        content = getattr(result, "content", None)
        if isinstance(content, list):
            texts: list[str] = []
            for c in content:
                text = getattr(c, "text", None)
                if text is not None:
                    texts.append(str(text))
                else:
                    texts.append(str(c))
            return "\n".join(texts)
    except Exception:
        pass
    return str(result)


@app.post("/mcp/debug/list", summary="调试：列出 MCP 工具")
async def mcp_debug_list(req: MCPDebugListRequest):
    try:
        from fastmcp import Client
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"fastmcp 不可用: {e}")

    try:
        client_ctx = Client.from_url(req.url) if hasattr(Client, "from_url") else Client(req.url)
        async with client_ctx as client:
            tools = await asyncio.wait_for(client.list_tools(), timeout=req.timeout_seconds)
            items = []
            for t in tools or []:
                items.append({
                    "name": getattr(t, "name", ""),
                    "description": getattr(t, "description", ""),
                })
            return {"ok": True, "url": req.url, "tools": items, "count": len(items)}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="连接 MCP 超时")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"列工具失败: {e}")


@app.post("/mcp/debug/call", summary="调试：调用 MCP 工具")
async def mcp_debug_call(req: MCPDebugCallRequest):
    try:
        from fastmcp import Client
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"fastmcp 不可用: {e}")

    try:
        client_ctx = Client.from_url(req.url) if hasattr(Client, "from_url") else Client(req.url)
        async with client_ctx as client:
            result = await asyncio.wait_for(
                client.call_tool(req.tool_name, req.args or {}),
                timeout=req.timeout_seconds,
            )
            return {
                "ok": True,
                "url": req.url,
                "tool_name": req.tool_name,
                "args": req.args,
                "result_text": _extract_mcp_result_text(result),
                "result_raw": str(result),
            }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="调用 MCP 工具超时")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"调用失败: {e}")


# ============================================================
# 消息分类辅助
# ============================================================

def _classify_message(msg) -> dict[str, Any]:
    """
    将 LangChain Message 分类为前端可识别的事件字段。
    返回 dict 包含: message_type, content, tool_name, tool_call_id
    """
    content = getattr(msg, "content", "")

    if isinstance(msg, ToolMessage):
        tool_name = getattr(msg, "name", "") or ""
        tool_call_id = getattr(msg, "tool_call_id", "") or ""
        return {
            "message_type": "tool",
            "content": content,
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
        }

    if isinstance(msg, AIMessage):
        # AI 消息带 tool_calls 的是"调用请求"，不是最终回复
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            # 提取调用摘要给前端展示（可选）
            call_summaries = []
            for tc in tool_calls:
                name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                call_summaries.append(name)
            return {
                "message_type": "tool_call",
                "content": content,
                "tool_names": call_summaries,
            }
        # 普通 AI 回复
        return {
            "message_type": "assistant",
            "content": content,
        }

    # 兜底
    return {
        "message_type": "unknown",
        "content": content,
    }


def _extract_node_events(node_name: str, node_value: dict) -> list[dict[str, Any]]:
    """
    从一个节点输出中提取所有消息事件。
    每条消息独立一个事件，带 message_type 区分。
    """
    events = []
    node_messages = node_value.get("messages") if isinstance(node_value, dict) else None
    if not node_messages:
        return events

    for msg in node_messages:
        classified = _classify_message(msg)
        content = classified.get("content", "")

        # 跳过空内容的 tool_call 请求（前端不需要看到空的调用指令）
        if classified["message_type"] == "tool_call" and not content:
            # 但仍然发一个"正在调用工具"的提示
            event = {
                "node": node_name,
                "message_type": "tool_call",
                "message": f"正在调用工具: {', '.join(classified.get('tool_names', []))}",
                "tool_names": classified.get("tool_names", []),
            }
            events.append(event)
            continue

        event: dict[str, Any] = {
            "node": node_name,
            "message_type": classified["message_type"],
            "message": content,
        }

        if classified["message_type"] == "tool":
            event["tool_name"] = classified.get("tool_name", "")
            event["tool_call_id"] = classified.get("tool_call_id", "")

        if classified["message_type"] == "tool_call":
            event["tool_names"] = classified.get("tool_names", [])

        events.append(event)

    return events


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

    try:
        session_service = SessionService()
        session_service.append_chat_message(session_id, "user", request_content, app_id=app_id)
        if response_content:
            session_service.append_chat_message(
                session_id, "assistant", response_content,
                app_id=app_id,
                model_name=collector.final_model or "",
                agent_name=collector.final_agent or "",
            )
        logger.info(f"会话记忆已保存: session={session_id}")
    except Exception as e:
        logger.error(f"保存会话记忆失败: {e}", exc_info=True)

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
            "model_detail": collector.call_details if collector.call_details else None,
            "final_model": collector.final_model,
            "cached_tokens": collector.cached_tokens or 0,
            "cache_hit_calls": collector.cache_hit_calls or 0,
            "cache_hit": bool(collector.cache_hit_calls > 0),
        }
        await log_service.save_log_async(log_data)
        logger.info(
            f"会话日志已保存: session={session_id}, "
            f"tokens={collector.total_tokens}, "
            f"models={[d['model'] for d in collector.call_details]}"
        )
    except Exception as e:
        logger.error(f"保存会话日志失败: {e}", exc_info=True)

def _build_session_file_refs(session_service: SessionService, session_id: str, app_id: str) -> list[dict[str, Any]]:
    files = session_service.get_session_files_content(session_id, app_id=app_id) or []
    result: list[dict[str, Any]] = []
    for f in files:
        result.append({
            "file_id": f.get("file_id") or "",
            "file_name": f.get("file_name") or "",
            "main_info": f.get("main_info") or {},
        })
    return result

def _print_request_token_summary(
    endpoint: str,
    session_id: str,
    app_id: str,
    scene_id: str,
    collector: UsageCollector,
):
    logger.info(
        f"[TOKEN][REQ] endpoint={endpoint} app_id={app_id} scene_id={scene_id} session_id={session_id} "
        f"calls={len(collector.call_details)} total={collector.total_tokens} "
        f"prompt={collector.prompt_tokens} completion={collector.completion_tokens} "
        f"final_model={collector.final_model} final_agent={collector.final_agent} "
        f"errors={collector.error_count} "
        f"cached_tokens={collector.cached_tokens} cache_hit_calls={collector.cache_hit_calls} "
    )
    if collector.last_error:
        logger.info(f"[TOKEN][REQ][LAST_ERROR] {collector.last_error}")


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
    session_files = _build_session_file_refs(session_service, req.session_id, app_id)
    if session_files:
        messages.append((
            "system",
            "当前会话已挂靠文件信息如下:\n"
            + json.dumps(session_files, ensure_ascii=False)
        ))
    messages.append(("user", req.message))

    inputs = {
        "session_id": req.session_id,
        "app_id": app_id,
        "scene_id": req.scene_id or "default",
        "selected_role_id": req.role_id or "",  # ← 新增
        "messages": messages,
        "session_files": session_files,
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
            # ---- 节点级元信息 ----
            base_meta: dict[str, Any] = {}
            if isinstance(node_value, dict):
                if node_name == "Supervisor":
                    role_name = node_value.get("role_name")
                    if role_name:
                        base_meta["role"] = role_name
                    if node_value.get("current_agent"):
                        base_meta["sub_agent"] = node_value["current_agent"]

                if node_name in ("GenericAgentRunner", "GenericToolRunner"):
                    if node_value.get("current_agent"):
                        base_meta["sub_agent"] = node_value["current_agent"]

            # ---- 逐条消息生成事件 ----
            msg_events = _extract_node_events(node_name, node_value) if isinstance(node_value, dict) else []

            if msg_events:
                for me in msg_events:
                    me.update(base_meta)  # 合入 role / sub_agent
                    events.append(me)
                    # 只有 assistant 类型的消息才算最终回复
                    if me.get("message_type") == "assistant":
                        content = me.get("message", "")
                        if isinstance(content, str) and content.strip():
                            final_message = content
            else:
                # 无消息的节点（如 Supervisor 只做路由）
                event = {"node": node_name, **base_meta}
                events.append(event)

    _print_request_token_summary(
        endpoint="/chat",
        session_id=req.session_id,
        app_id=app_id,
        scene_id=req.scene_id or "default",
        collector=collector,
    )

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
    session_files = _build_session_file_refs(session_service, req.session_id, app_id)
    files_json = json.dumps(session_files or [], ensure_ascii=False)
    messages.append((
        "system",
        f"当前会话挂靠文件信息如下（为空数组表示无挂靠）:\n<files>\n{files_json}\n</files>"
    ))
    messages.append(("user", req.message))

    inputs = {
        "session_id": req.session_id,
        "app_id": app_id,
        "scene_id": req.scene_id or "default",
        "selected_role_id": req.role_id or "",  # ← 新增
        "messages": messages,
        "session_files": session_files,
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
                # ---- 节点级元信息 ----
                base_meta: dict[str, Any] = {}
                if isinstance(node_value, dict):
                    if node_name == "Supervisor":
                        role_name = node_value.get("role_name")
                        if role_name:
                            base_meta["role"] = role_name
                        if node_value.get("current_agent"):
                            base_meta["sub_agent"] = node_value["current_agent"]

                    if node_name in ("GenericAgentRunner", "GenericToolRunner"):
                        if node_value.get("current_agent"):
                            base_meta["sub_agent"] = node_value["current_agent"]

                # ---- 逐条消息生成事件 ----
                msg_events = _extract_node_events(node_name, node_value) if isinstance(node_value, dict) else []

                if msg_events:
                    for me in msg_events:
                        me.update(base_meta)
                        # 只有 assistant 类型才更新 final_message
                        if me.get("message_type") == "assistant":
                            content = me.get("message", "")
                            if isinstance(content, str) and content.strip():
                                final_message = content
                        yield f"event: node\ndata: {json.dumps(me, ensure_ascii=False)}\n\n"
                else:
                    payload = {"node": node_name, **base_meta}
                    yield f"event: node\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        _print_request_token_summary(
            endpoint="/chat/stream",
            session_id=req.session_id,
            app_id=app_id,
            scene_id=req.scene_id or "default",
            collector=collector,
        )

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
