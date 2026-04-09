# -*- coding: utf-8 -*-
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from .database import Database
from .CRUD import CRUD
from Schema import FileModel, MemoryModel, FileTypeModel, SessionModel



class FileService:
    def __init__(self):
        self.crud = CRUD(Database.get_session)
        self.collection = "files"

    def _file_query(self, file_id: str, app_id: str = "") -> Dict[str, str]:
        """构建 file_id + app_id 的查询条件"""
        query = {"file_id": file_id}
        if app_id:
            query["app_id"] = app_id
        return query

    def get_file_info(self, file_id: str, app_id: str = None) -> Optional[Dict]:
        query = {"file_id": file_id}
        if app_id:
            query["app_id"] = app_id
        return self.crud.find_one(self.collection, query)

    def get_files_by_app(self, app_id: str) -> List[Dict]:
        return self.crud.find_documents(self.collection, {"app_id": app_id})

    def save_file_info(self, file_info: FileModel) -> str:
        """保存文件信息，按 file_id + app_id 去重"""
        query = self._file_query(file_info.file_id, file_info.app_id)
        hit = self.crud.find_one(self.collection, query)
        if hit:
            return hit["_id"]

        doc = file_info.model_dump(by_alias=True, exclude_none=True, exclude={'id'})
        doc.pop("_id", None)  # 确保不带 _id，让数据库自动生成
        return self.crud.insert_document(self.collection, doc)

    def update_file_info(self, file_id: str, update_data: FileModel, app_id: str = "") -> int:
        query = self._file_query(file_id, app_id)
        data = update_data.model_dump(exclude_none=True, exclude={'id', 'file_id'})
        return self.crud.update_document(self.collection, query, data)

    def delete_file_info(self, file_id: str, app_id: str = "") -> int:
        query = self._file_query(file_id, app_id)
        return self.crud.delete_document(self.collection, query)

    def update_processing_status(
        self,
        file_id: str,
        app_id: str,
        processing_status: str,
        processing_stage: str,
        processing_message: str = "",
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> int:
        # 改这里：不要再用 _id=file_id
        query: Dict[str, Any] = {"file_id": file_id}
        if app_id:
            query["app_id"] = app_id

        patch: Dict[str, Any] = {
            "processing_status": processing_status,
            "processing_stage": processing_stage,
            "processing_message": processing_message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra_fields:
            patch.update(extra_fields)

        return self.crud.update_document(self.collection, query, patch)

    def get_processing_status(self, file_id: str, app_id: str = "") -> Optional[Dict[str, Any]]:
        doc = self.get_file_info(file_id, app_id=app_id)
        if not doc:
            return None
        return {
            "app_id": doc.get("app_id", ""),
            "file_id": doc.get("file_id", file_id),
            "file_name": doc.get("file_name", ""),
            "processing_status": doc.get("processing_status", "unknown"),
            "processing_stage": doc.get("processing_stage"),
            "processing_message": doc.get("processing_message"),
            "updated_at": doc.get("updated_at"),
            "upload_time": doc.get("upload_time"),
        }


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
        allowed = {
            "status",
            "metadata",
            "pending_status",
            "pending_data",
            "pending_expires_at",
        }
        for k, v in kwargs.items():
            if k in allowed and v is not None:
                patch[k] = v
        return self.crud.update_document(self.collection, query, patch)

    # ------------------------
    # HITL 挂起/恢复
    # ------------------------
    def suspend_session(
        self,
        session_id: str,
        app_id: str,
        interaction_id: str,
        question: str,
        input_type: str,
        expected_input: Optional[List[str]] = None,
        expected_schema: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 300,
        context: Optional[Dict[str, Any]] = None,
    ) -> int:
        now_ts = datetime.now(timezone.utc)
        expires_at = now_ts.timestamp() + max(int(timeout_seconds), 1)

        pending_data: Dict[str, Any] = {
            "interaction_id": interaction_id,
            "question": question,
            "input_type": input_type,
            "expected_input": expected_input or [],
            "expected_schema": expected_schema or {},
            "timeout_seconds": timeout_seconds,
            "suspended_at": now_ts.isoformat(),
            "context": context or {},
            "resumed": False,
        }

        return self.update_session(
            session_id,
            app_id=app_id,
            pending_status="suspended",
            pending_data=pending_data,
            pending_expires_at=datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
        )

    def get_pending_interaction(self, session_id: str, app_id: str = "") -> Optional[Dict[str, Any]]:
        doc = self.get_session_metadata(session_id, app_id=app_id)
        if not doc:
            return None
        pending_status = (doc.get("pending_status") or "active")
        if pending_status != "suspended":
            return None

        # 读取时顺带做超时判定，避免长时间停留在 suspended
        expires_at = doc.get("pending_expires_at")
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > exp_dt:
                    self.mark_pending_timeout(session_id, app_id=app_id)
                    return {
                        "pending_status": "timeout_failed",
                        "pending_data": doc.get("pending_data") or {},
                        "pending_expires_at": expires_at,
                    }
            except Exception:
                pass

        return {
            "pending_status": pending_status,
            "pending_data": doc.get("pending_data") or {},
            "pending_expires_at": doc.get("pending_expires_at"),
        }

    def mark_pending_timeout(self, session_id: str, app_id: str = "") -> int:
        pending = self.get_pending_interaction(session_id, app_id=app_id)
        if not pending:
            return 0

        pd = pending.get("pending_data") or {}
        pd["timeout_at"] = self._now_iso()
        pd["timeout_reason"] = "user_input_timeout"

        return self.update_session(
            session_id,
            app_id=app_id,
            pending_status="timeout_failed",
            pending_data=pd,
            pending_expires_at=None,
        )

    def resume_pending_interaction(
        self,
        session_id: str,
        app_id: str,
        interaction_id: str,
        user_input: Any,
    ) -> Dict[str, Any]:
        session_doc = self.get_session_metadata(session_id, app_id=app_id)
        if not session_doc:
            return {"ok": False, "code": "SESSION_NOT_FOUND", "message": "session 不存在"}

        pending_status = session_doc.get("pending_status") or "active"
        pending_data = session_doc.get("pending_data") or {}

        if pending_status != "suspended":
            if pending_status == "timeout_failed":
                return {"ok": False, "code": "PENDING_TIMEOUT", "message": "该交互已超时"}
            return {"ok": False, "code": "NO_PENDING", "message": "当前会话无挂起交互"}

        current_interaction = (pending_data.get("interaction_id") or "").strip()
        if interaction_id and current_interaction and interaction_id != current_interaction:
            return {"ok": False, "code": "INTERACTION_MISMATCH", "message": "interaction_id 不匹配"}

        expires_at = session_doc.get("pending_expires_at")
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > exp_dt:
                    self.mark_pending_timeout(session_id, app_id=app_id)
                    return {"ok": False, "code": "PENDING_TIMEOUT", "message": "该交互已超时"}
            except Exception:
                pass

        if pending_data.get("resumed"):
            return {
                "ok": True,
                "code": "ALREADY_RESUMED",
                "message": "该交互已恢复",
                "pending_data": pending_data,
            }

        pending_data["user_input"] = user_input
        pending_data["resumed"] = True
        pending_data["resumed_at"] = self._now_iso()

        self.update_session(
            session_id,
            app_id=app_id,
            pending_status="active",
            pending_data=pending_data,
            pending_expires_at=None,
        )

        return {
            "ok": True,
            "code": "RESUMED",
            "message": "交互已恢复",
            "pending_data": pending_data,
        }

    def build_resume_graph_inputs(self, session_id: str, app_id: str) -> Optional[Dict[str, Any]]:
        """从已恢复的 pending_data 构建图继续执行所需 inputs。"""
        session_doc = self.get_session_metadata(session_id, app_id=app_id)
        if not session_doc:
            return None

        pending_data = session_doc.get("pending_data") or {}
        if not pending_data.get("resumed"):
            return None

        context = pending_data.get("context") or {}
        user_input = pending_data.get("user_input")
        question = pending_data.get("question") or ""
        current_agent = context.get("current_agent") or ""

        # 组装一条用户消息继续驱动图执行
        if isinstance(user_input, (dict, list)):
            user_input_text = json.dumps(user_input, ensure_ascii=False)
        else:
            user_input_text = str(user_input)

        followup_message = user_input_text.strip() if user_input_text else ""
        if question and followup_message:
            followup_message = f"【HITL用户输入】问题：{question}\n用户输入：{followup_message}"
        elif not followup_message:
            followup_message = "【HITL用户输入】（空输入）"

        session_files = self.get_session_files_content(session_id, app_id=app_id)

        return {
            "session_id": session_id,
            "app_id": app_id,
            "scene_id": context.get("scene_id") or "default",
            "selected_role_id": context.get("selected_role_id") or "",
            "current_agent": current_agent,
            "next": "RUN_AGENT" if current_agent else "",
            "messages": [("user", followup_message)],
            "session_files": [
                {
                    "file_id": f.get("file_id") or "",
                    "file_name": f.get("file_name") or "",
                    "main_info": f.get("main_info") or {},
                }
                for f in (session_files or [])
            ],
        }

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

        # ===== 改动：用 file_id 字段查，不再用 _id =====
        file_query: Dict[str, Any] = {"file_id": {"$in": target_ids}}
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
