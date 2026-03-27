# -*- coding: utf-8 -*-
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from .database import Database
from .CRUD import CRUD
from .Schema import FileModel, MemoryModel, FileTypeModel, SessionModel



class FileService:
    def __init__(self):
        self.crud = CRUD(Database.get_session)
        self.collection = "files"

    def get_file_info(self, file_id: str, app_id: str = None) -> Optional[Dict]:
        doc = self.crud.find_one(self.collection, {"_id": file_id})
        if doc and app_id and doc.get("app_id", "") != app_id:
            return None
        return doc

    def get_files_by_app(self, app_id: str) -> List[Dict]:
        return self.crud.find_documents(self.collection, {"app_id": app_id})

    def save_file_info(self, file_info: FileModel) -> str:
        doc = file_info.model_dump(by_alias=True, exclude_none=True, exclude={'id'})
        doc["_id"] = file_info.file_id

        if hit := self.crud.find_one(self.collection, {"_id": file_info.file_id}):
            # 兼容历史数据：旧记录 app_id 为空时，使用本次上传的 app_id 回填
            hit_app_id = (hit.get("app_id") or "").strip()
            new_app_id = (file_info.app_id or "").strip()
            if not hit_app_id and new_app_id:
                self.crud.update_document(
                    self.collection,
                    {"_id": file_info.file_id},
                    {"app_id": new_app_id}
                )
            return hit["_id"]

        return self.crud.insert_document(self.collection, doc)

    def update_file_info(self, file_id: str, update_data: FileModel) -> int:
        data = update_data.model_dump(exclude_none=True, exclude={'id', 'file_id'})
        return self.crud.update_document(self.collection, {"_id": file_id}, data)

    def delete_file_info(self, file_id: str) -> int:
        return self.crud.delete_document(self.collection, {"_id": file_id})


class MemoryService:
    def __init__(self):
        self.crud = CRUD(Database.get_session)
        self.collection = "memories"

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        app_id: str = "",
        model_name: str = "",
        agent_name: str = "",
    ):
        """追加一条消息到该 session 的 memory 记录，不存在则创建"""
        if not content or not content.strip():
            return None

        query = {"session_id": session_id}
        if app_id:
            query["app_id"] = app_id

        msg: Dict[str, Any] = {
            "role": role,
            "content": content,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        if model_name:
            msg["model"] = model_name
        if agent_name:
            msg["agent"] = agent_name

        doc = self.crud.find_one(self.collection, query)
        if doc:
            messages = doc.get("messages", [])
            messages.append(msg)
            return self.crud.update_document(
                self.collection,
                query,
                {
                    "messages": messages,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            )
        else:
            return self.crud.insert_document(self.collection, {
                "app_id": app_id,
                "session_id": session_id,
                "messages": [msg],
                "updated_at": datetime.now(timezone.utc).isoformat()
            })

    def get_recent_messages(self, session_id: str, last_n: int = 20, app_id: str = None) -> List[Dict[str, str]]:
        """获取最近 N 条消息"""
        query = {"session_id": session_id}
        if app_id:
            query["app_id"] = app_id

        doc = self.crud.find_one(self.collection, query)
        if not doc:
            return []

        messages = doc.get("messages", [])
        return messages[-last_n:] if last_n else messages

    def get_memory_doc(self, session_id: str, app_id: str = "") -> Optional[Dict]:
        """返回完整 memory 文档（含 _id, updated_at 等元信息）"""
        query = {"session_id": session_id}
        if app_id:
            query["app_id"] = app_id
        return self.crud.find_one(self.collection, query)

    def update_messages(self, session_id: str, messages: List[Dict[str, Any]], app_id: str = "") -> int:
        """整体替换消息列表（用于编辑/修正历史）"""
        query = {"session_id": session_id}
        if app_id:
            query["app_id"] = app_id

        doc = self.crud.find_one(self.collection, query)
        if doc:
            return self.crud.update_document(
                self.collection,
                query,
                {
                    "messages": messages,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            )
        else:
            # 不存在则创建
            return self.crud.insert_document(self.collection, {
                "app_id": app_id,
                "session_id": session_id,
                "messages": messages,
                "updated_at": datetime.now(timezone.utc).isoformat()
            })

    def delete_memories_by_session(self, session_id: str, app_id: str) -> int:
        query = {"session_id": session_id, "app_id": app_id}
        return self.crud.delete_document(self.collection, query)



class FileTypeService:
    def __init__(self):
        self.crud = CRUD(Database.get_session)
        self.collection = "config"

    def update_file_types(self, model: FileTypeModel):
        self.crud.update_document(
            self.collection,
            {"_id": "global_file_types"},
            model.model_dump(), upsert=True
        )

    def get_file_types(self) -> List[str]:
        doc = self.crud.find_one(self.collection, {"_id": "global_file_types"})
        return doc.get("file_type", []) if doc else []


class SessionService:
    def __init__(self):
        self.crud = CRUD(Database.get_session)
        self.collection = "sessions"
        self.memory_service = MemoryService()
        self.file_service = FileService()

    # ------------------------
    # 内部工具
    # ------------------------
    def _session_query(self, session_id: str, app_id: str = "") -> Dict[str, str]:
        query = {"session_id": session_id}
        if app_id:
            query["app_id"] = app_id
        return query

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------
    # 会话元数据
    # ------------------------
    def get_session(self, session_id: str, app_id: str = None) -> Optional[SessionModel]:
        query = self._session_query(session_id, app_id or "")
        data = self.crud.find_one(self.collection, query)
        return SessionModel(**data) if data else None

    def get_session_metadata(self, session_id: str, app_id: str = "") -> Optional[Dict]:
        """返回 sessions 原始文档（包含扩展字段，如 updated_at/status/metadata）"""
        query = self._session_query(session_id, app_id)
        return self.crud.find_one(self.collection, query)

    def get_sessions_by_app(self, app_id: str) -> List[Dict]:
        return self.crud.find_documents(self.collection, {"app_id": app_id})

    def create_session(
        self,
        session_id: str,
        app_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        status: str = "active",
        upsert: bool = True,
    ) -> str:
        query = self._session_query(session_id, app_id)
        existing = self.crud.find_one(self.collection, query)
        now = self._now_iso()

        if existing:
            if upsert:
                patch = {
                    "updated_at": now,
                    "status": existing.get("status", status),
                    "metadata": existing.get("metadata", metadata or {}),
                }
                self.crud.update_document(self.collection, query, patch)
            return existing["_id"]

        doc = {
            "app_id": app_id,
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "status": status,
            "metadata": metadata or {},
            "file_list": [],
        }
        return self.crud.insert_document(self.collection, doc)

    def ensure_session(self, session_id: str, app_id: str = "") -> str:
        query = self._session_query(session_id, app_id)
        existing = self.crud.find_one(self.collection, query)
        if existing:
            return existing["_id"]
        return self.create_session(session_id=session_id, app_id=app_id)

    def touch_session(self, session_id: str, app_id: str = "", extra_patch: Optional[Dict[str, Any]] = None) -> int:
        query = self._session_query(session_id, app_id)
        patch = {"updated_at": self._now_iso()}
        if extra_patch:
            patch.update(extra_patch)

        count = self.crud.update_document(self.collection, query, patch)
        if count == 0:
            self.create_session(session_id=session_id, app_id=app_id)
            return 1
        return count

    def update_session(self, session_id: str, app_id: str = "", **kwargs) -> int:
        """更新会话的任意字段（status, metadata 等）"""
        query = self._session_query(session_id, app_id)
        patch = {"updated_at": self._now_iso()}
        # 只接受合法字段
        allowed = {"status", "metadata"}
        for k, v in kwargs.items():
            if k in allowed and v is not None:
                patch[k] = v
        return self.crud.update_document(self.collection, query, patch)

    # ------------------------
    # 文件关联
    # ------------------------
    def add_file_to_session(self, session_id: str, file_info: FileModel, app_id: str = ""):
        # 先保存文件
        self.file_service.save_file_info(file_info)

        # 确保 session 存在
        self.ensure_session(session_id, app_id=app_id)

        query = self._session_query(session_id, app_id)
        doc = self.crud.find_one(self.collection, query) or {}

        current_list = doc.get("file_list", []) or []
        if file_info.file_id not in current_list:
            current_list.append(file_info.file_id)

        self.crud.update_document(
            self.collection,
            query,
            {
                "file_list": current_list,
                "updated_at": self._now_iso(),
            }
        )
        return file_info.file_id

    def mount_file_to_session(self, session_id: str, file_id: str, app_id: str = "") -> bool:
        """
        轻量版：只把已存在的 file_id 挂载到 session 的 file_list。
        不重复保存文件（文件已通过 /upload 存在）。
        返回 True 表示新挂载，False 表示已存在或 file 不存在。
        """
        # 校验文件存在
        file_doc = self.file_service.get_file_info(file_id, app_id=app_id)
        if not file_doc:
            return False

        self.ensure_session(session_id, app_id=app_id)

        query = self._session_query(session_id, app_id)
        doc = self.crud.find_one(self.collection, query) or {}

        current_list = doc.get("file_list", []) or []
        if file_id in current_list:
            return False  # 已挂载

        current_list.append(file_id)
        self.crud.update_document(
            self.collection,
            query,
            {
                "file_list": current_list,
                "updated_at": self._now_iso(),
            }
        )
        return True

    def remove_file_from_session(self, session_id: str, file_id: str, app_id: str = "") -> int:
        query = self._session_query(session_id, app_id)
        doc = self.crud.find_one(self.collection, query)
        if not doc:
            return 0

        current_list = doc.get("file_list", []) or []
        if file_id not in current_list:
            return 0

        current_list.remove(file_id)
        self.crud.update_document(
            self.collection,
            query,
            {
                "file_list": current_list,
                "updated_at": self._now_iso(),
            }
        )
        return 1

    def get_session_files_content(self, session_id: str, file_id: Optional[str] = None, app_id: str = None) -> List[Dict]:
        session = self.get_session(session_id, app_id=app_id)
        if not session or not session.file_list:
            return []

        if file_id:
            if file_id not in session.file_list:
                return []
            target_ids = [file_id]
        else:
            target_ids = session.file_list

        file_query: Dict[str, Any] = {"_id": {"$in": target_ids}}
        if app_id:
            file_query["app_id"] = app_id

        files_data = self.crud.find_documents("files", file_query)
        return files_data

    # ------------------------
    # 对话相关（兼容旧调用）
    # ------------------------
    def append_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        app_id: str = "",
        model_name: str = "",
        agent_name: str = "",
    ):
        self.ensure_session(session_id, app_id=app_id)
        ret = self.memory_service.append_message(
            session_id, role, content,
            app_id=app_id,
            model_name=model_name,
            agent_name=agent_name,
        )
        self.touch_session(session_id, app_id=app_id)
        return ret


    def get_full_context(self, session_id: str, last_n: int = 20, app_id: str = None) -> Dict:
        history = self.memory_service.get_recent_messages(session_id, last_n, app_id=app_id)
        files = self.get_session_files_content(session_id, app_id=app_id)
        return {
            "history": history,
            "files": files
        }

    # ------------------------
    # 删除
    # ------------------------
    def delete_everything_about_session(self, session_id: str, app_id: str):
        self.memory_service.delete_memories_by_session(session_id, app_id=app_id)
        query = {"session_id": session_id, "app_id": app_id}
        deleted_count = self.crud.delete_document(self.collection, query)
        return deleted_count
