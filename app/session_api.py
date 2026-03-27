# -*- coding: utf-8 -*-
"""
会话 & 记忆 管理接口
路由前缀：/sessions, /memories
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query

from dataBase.Service import SessionService, MemoryService, FileService
from app.Schema import (
    CreateSessionRequest,
    UpdateSessionRequest,
    AppendMessageRequest,
    ReplaceMessagesRequest,
)

router = APIRouter(tags=["Sessions & Memories"])

# ============================================================
# Sessions
# ============================================================

@router.get("/sessions", summary="查询会话列表（按 app_id）")
def list_sessions(app_id: str = Query(..., description="应用ID")) -> List[Dict]:
    svc = SessionService()
    return svc.get_sessions_by_app(app_id)


@router.get("/sessions/{session_id}", summary="查询单个会话详情")
def get_session(
    session_id: str,
    app_id: str = Query("", description="应用ID"),
) -> Dict:
    svc = SessionService()
    doc = svc.get_session_metadata(session_id, app_id=app_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return doc


@router.post("/sessions", summary="创建会话")
def create_session(req: CreateSessionRequest) -> Dict[str, Any]:
    svc = SessionService()
    doc_id = svc.create_session(
        session_id=req.session_id,
        app_id=req.app_id,
        metadata=req.metadata,
        status=req.status,
    )
    return {
        "id": doc_id,
        "session_id": req.session_id,
        "app_id": req.app_id,
        "status": req.status,
        "message": "created",
    }


@router.put("/sessions/{session_id}", summary="更新会话（status / metadata）")
def update_session(session_id: str, req: UpdateSessionRequest) -> Dict[str, Any]:
    svc = SessionService()

    # 先确认存在
    existing = svc.get_session_metadata(session_id, app_id=req.app_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    count = svc.update_session(
        session_id=session_id,
        app_id=req.app_id,
        status=req.status,
        metadata=req.metadata,
    )
    return {"session_id": session_id, "updated": count}


@router.delete("/sessions/{session_id}", summary="删除会话（连带 memories）")
def delete_session(
    session_id: str,
    app_id: str = Query("", description="应用ID"),
) -> Dict[str, Any]:
    svc = SessionService()

    existing = svc.get_session_metadata(session_id, app_id=app_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    deleted = svc.delete_everything_about_session(session_id, app_id=app_id)
    return {"session_id": session_id, "deleted": deleted, "message": "session and memories deleted"}


# ============================================================
# Session Files（文件挂载管理）
# ============================================================

@router.get("/files/{file_id}/content", summary="按 app_id + file_id 获取文件内容")
def get_file_content(
    file_id: str,
    app_id: str = Query(..., description="应用ID"),
) -> Dict[str, Any]:
    file_svc = FileService()
    doc = file_svc.get_file_info(file_id=file_id, app_id=app_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"File '{file_id}' not found")

    return {
        "app_id": doc.get("app_id", ""),
        "file_id": doc.get("file_id", file_id),
        "file_name": doc.get("file_name", ""),
        "file_type": doc.get("file_type", []),
        "content": doc.get("content", ""),
        "main_info": doc.get("main_info"),
        "upload_time": doc.get("upload_time"),
    }

@router.get("/sessions/{session_id}/files", summary="查询会话关联的文件")
def get_session_files(
    session_id: str,
    app_id: str = Query("", description="应用ID"),
) -> List[Dict]:
    svc = SessionService()
    return svc.get_session_files_content(session_id, app_id=app_id)


@router.post("/sessions/{session_id}/files/{file_id}", summary="挂载文件到会话")
def mount_file_to_session(
    session_id: str,
    file_id: str,
    app_id: str = Query("", description="应用ID"),
) -> Dict[str, Any]:
    svc = SessionService()
    mounted = svc.mount_file_to_session(session_id, file_id, app_id=app_id)
    if not mounted:
        raise HTTPException(
            status_code=400,
            detail=f"File '{file_id}' not found or already mounted"
        )
    return {"session_id": session_id, "file_id": file_id, "message": "mounted"}


@router.delete("/sessions/{session_id}/files/{file_id}", summary="从会话移除文件")
def unmount_file_from_session(
    session_id: str,
    file_id: str,
    app_id: str = Query("", description="应用ID"),
) -> Dict[str, Any]:
    svc = SessionService()
    removed = svc.remove_file_from_session(session_id, file_id, app_id=app_id)
    if removed == 0:
        raise HTTPException(
            status_code=404,
            detail=f"File '{file_id}' not found in session '{session_id}'"
        )
    return {"session_id": session_id, "file_id": file_id, "message": "removed"}


# ============================================================
# Session Context（完整上下文）
# ============================================================

@router.get("/sessions/{session_id}/context", summary="查询完整上下文（历史 + 文件）")
def get_session_context(
    session_id: str,
    app_id: str = Query("", description="应用ID"),
    last_n: int = Query(20, description="最近N条消息"),
) -> Dict[str, Any]:
    svc = SessionService()
    return svc.get_full_context(session_id, last_n=last_n, app_id=app_id)


# ============================================================
# Memories（对话记忆）
# ============================================================

@router.get("/memories/{session_id}", summary="查询对话历史")
def get_memories(
    session_id: str,
    app_id: str = Query("", description="应用ID"),
    last_n: int = Query(0, description="最近N条，0=全部"),
) -> Dict[str, Any]:
    mem_svc = MemoryService()

    # 返回完整文档（含 updated_at 等元信息）
    doc = mem_svc.get_memory_doc(session_id, app_id=app_id)
    if not doc:
        return {"session_id": session_id, "messages": [], "total": 0}

    messages = doc.get("messages", [])
    total = len(messages)

    if last_n and last_n > 0:
        messages = messages[-last_n:]

    return {
        "session_id": session_id,
        "app_id": doc.get("app_id", ""),
        "messages": messages,
        "total": total,
        "updated_at": doc.get("updated_at"),
    }


@router.post("/memories/{session_id}", summary="追加一条消息")
def append_memory(session_id: str, req: AppendMessageRequest) -> Dict[str, Any]:
    mem_svc = MemoryService()
    result = mem_svc.append_message(
        session_id=session_id,
        role=req.role,
        content=req.content,
        app_id=req.app_id,
        model_name=req.model_name,
        agent_name=req.agent_name,
    )
    return {
        "session_id": session_id,
        "role": req.role,
        "message": "appended",
        "result": result,
    }


@router.put("/memories/{session_id}", summary="替换整个消息列表")
def replace_memories(session_id: str, req: ReplaceMessagesRequest) -> Dict[str, Any]:
    mem_svc = MemoryService()
    result = mem_svc.update_messages(
        session_id=session_id,
        messages=req.messages,
        app_id=req.app_id,
    )
    return {
        "session_id": session_id,
        "message_count": len(req.messages),
        "message": "replaced",
        "result": result,
    }


@router.delete("/memories/{session_id}", summary="清空会话记忆")
def delete_memories(
    session_id: str,
    app_id: str = Query("", description="应用ID"),
) -> Dict[str, Any]:
    mem_svc = MemoryService()

    # 先检查存在
    doc = mem_svc.get_memory_doc(session_id, app_id=app_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Memories for session '{session_id}' not found")

    deleted = mem_svc.delete_memories_by_session(session_id, app_id=app_id)
    return {"session_id": session_id, "deleted": deleted, "message": "memories cleared"}
