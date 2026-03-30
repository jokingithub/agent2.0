# -*- coding: utf-8 -*-
# 文件：app/file_api.py

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from dataBase.Service import FileService, SessionService
from logger import logger

router = APIRouter(prefix="", tags=["文件管理"])

_file_service = FileService()
_session_service = SessionService()


def _require_app_id(app_id: str) -> str:
    app_id = (app_id or "").strip()
    if not app_id:
        raise HTTPException(status_code=400, detail="app_id 不能为空")
    return app_id


def _to_file_item(doc: Dict[str, Any], with_content: bool = False) -> Dict[str, Any]:
    item = {
        "id": doc.get("_id", ""),
        "app_id": doc.get("app_id", ""),
        "file_id": doc.get("file_id", doc.get("_id", "")),
        "file_name": doc.get("file_name", ""),
        "file_type": doc.get("file_type", []),
        "file_path": doc.get("file_path"),
        "upload_time": doc.get("upload_time"),
        "main_info": doc.get("main_info"),
    }
    content = doc.get("content", "") or ""
    if with_content:
        item["content"] = content
    else:
        item["content_preview"] = content[:300]
    return item


@router.get("/files", summary="文件列表（支持按 app_id / session_id / file_type / keyword 过滤）")
def list_files(
    app_id: str = Query(..., description="应用ID（必填）"),
    session_id: str = Query("", description="会话ID（可选）"),
    file_type: str = Query("", description="文件类型（可选）"),
    keyword: str = Query("", description="关键词（匹配 file_name）"),
    limit: int = Query(200, ge=1, le=2000),
    with_content: bool = Query(False, description="是否返回全文 content"),
):
    app_id = _require_app_id(app_id)

    # 1) 先取候选集合
    if session_id:
        session = _session_service.get_session(session_id, app_id=app_id)
        if not session or not session.file_list:
            return {"items": [], "total": 0}

        query: Dict[str, Any] = {"_id": {"$in": session.file_list}, "app_id": app_id}
        docs = _file_service.crud.find_documents("files", query)
    else:
        docs = _file_service.get_files_by_app(app_id)

    # 2) Python 层过滤（兼容 JSONB 数组字段）
    ft = file_type.strip().lower()
    kw = keyword.strip().lower()

    def hit_type(d: Dict[str, Any]) -> bool:
        if not ft:
            return True
        types = d.get("file_type", [])
        if isinstance(types, list):
            return any(str(x).lower() == ft for x in types)
        return ft in str(types).lower()

    def hit_kw(d: Dict[str, Any]) -> bool:
        if not kw:
            return True
        return kw in str(d.get("file_name", "")).lower()

    docs = [d for d in docs if hit_type(d) and hit_kw(d)]

    # 3) 排序 + 限制
    docs.sort(key=lambda x: str(x.get("upload_time", "")), reverse=True)
    docs = docs[:limit]

    items = [_to_file_item(d, with_content=with_content) for d in docs]
    return {"items": items, "total": len(items)}


@router.get("/files/{file_id}", summary="文件详情")
def get_file_detail(
    file_id: str,
    app_id: str = Query(..., description="应用ID（必填）"),
    with_content: bool = Query(True, description="是否返回全文 content"),
):
    app_id = _require_app_id(app_id)

    doc = _file_service.get_file_info(file_id, app_id=app_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")

    return _to_file_item(doc, with_content=with_content)


@router.delete("/files/{file_id}", summary="删除文件（可选删除物理文件，自动解绑 sessions）")
def delete_file(
    file_id: str,
    app_id: str = Query(..., description="应用ID（必填）"),
    remove_physical: bool = Query(False, description="是否删除物理文件"),
):
    app_id = _require_app_id(app_id)

    doc = _file_service.get_file_info(file_id, app_id=app_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文件不存在")

    # 1) 从该 app 下所有 session 的 file_list 中解绑
    detached_count = 0
    sessions = _session_service.get_sessions_by_app(app_id)
    for s in sessions:
        sid = s.get("session_id", "")
        if not sid:
            continue
        if file_id in (s.get("file_list", []) or []):
            c = _session_service.remove_file_from_session(sid, file_id, app_id=app_id)
            detached_count += int(c or 0)

    # 2) 删除 files 表记录
    deleted = _file_service.delete_file_info(file_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="文件不存在或已删除")

    # 3) 可选删除物理文件
    physical_removed = False
    if remove_physical:
        file_path = doc.get("file_path")
        if file_path:
            try:
                p = Path(file_path)
                if p.exists() and p.is_file():
                    p.unlink()
                    physical_removed = True
            except Exception as e:
                logger.warning(f"删除物理文件失败 file_id={file_id}, path={file_path}, err={e}")

    return {
        "message": "文件删除成功",
        "file_id": file_id,
        "detached_sessions": detached_count,
        "physical_removed": physical_removed,
    }
