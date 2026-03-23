# -*- coding: utf-8 -*-
import json
from typing import Optional, List, Dict
from datetime import datetime
from .database import Database
from .CRUD import CRUD
from .Schema import FileModel, MemoryModel, FileTypeModel, SessionModel


class FileService:
    def __init__(self):
        self.crud = CRUD(Database.get_session)  # 改这里
        self.collection = "files"

    def get_file_info(self, file_id: str) -> Optional[Dict]:
        return self.crud.find_one(self.collection, {"file_id": file_id})

    def save_file_info(self, file_info: FileModel) -> str:
        if hit := self.get_file_info(file_info.file_id):
            return hit["_id"]
        doc = file_info.model_dump(by_alias=True, exclude_none=True)
        return self.crud.insert_document(self.collection, doc)

    def update_file_info(self, file_id: str, update_data: FileModel) -> int:
        data = update_data.model_dump(exclude_none=True, exclude={'id'})
        return self.crud.update_document(self.collection, {"file_id": file_id}, data)

    def delete_file_info(self, file_id: str) -> int:
        return self.crud.delete_document(self.collection, {"file_id": file_id})


class MemoryService:
    def __init__(self):
        self.crud = CRUD(Database.get_session)  # 改这里
        self.collection = "memories"

    def save_memory(self, session_id: str, role: str, content: str):
        doc = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()  # 改成字符串，JSONB里好排序
        }
        return self.crud.insert_document(self.collection, doc)

    def get_recent_memories(self, session_id: str, last_n: int = 10) -> List[Dict]:
        mems = self.crud.find_documents(
            self.collection,
            {"session_id": session_id},
            sort_by="timestamp",
            ascending=False,
            limit=last_n
        )
        return mems[::-1]

    def delete_memories_by_session(self, session_id: str) -> int:
        return self.crud.delete_document(self.collection, {"session_id": session_id})


class FileTypeService:
    def __init__(self):
        self.crud = CRUD(Database.get_session)  # 改这里
        self.collection = "config"

    def update_file_types(self, model: FileTypeModel):
        self.crud.update_document(
            self.collection,
            {"_id": "global_file_types"},
            model.model_dump(),upsert=True
        )

    def get_file_types(self) -> List[str]:
        doc = self.crud.find_one(self.collection, {"_id": "global_file_types"})
        return doc.get("file_type", []) if doc else []


class SessionService:
    def __init__(self):
        self.crud = CRUD(Database.get_session)  # 改这里
        self.collection = "sessions"
        self.memory_service = MemoryService()
        self.file_service = FileService()

    def get_session(self, session_id: str) -> Optional[SessionModel]:
        data = self.crud.find_one(self.collection, {"session_id": session_id})
        return SessionModel(**data) if data else None

    # --- 文件的集成管理 ---

    def add_file_to_session(self, session_id: str, file_info: FileModel):
        """
        原来用MongoDB 的 $addToSet，现在改成：
        1. 查出当前 file_list
        2. 去重追加
        3. 写回去
        """
        self.file_service.save_file_info(file_info)

        session = self.get_session(session_id)

        if session is None:
            # 会话不存在，创建新会话
            doc = {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "file_list": [file_info.file_id]
            }
            self.crud.insert_document(self.collection, doc)
        else:
            # 会话存在，去重追加 file_id
            current_list = session.file_list or []
            if file_info.file_id not in current_list:
                current_list.append(file_info.file_id)
                self.crud.update_document(
                    self.collection,
                    {"session_id": session_id},
                    {"file_list": current_list}
                )

        return file_info.file_id

    def remove_file_from_session(self, session_id: str, file_id: str) -> int:
        """
        原来用 MongoDB 的 $pull，现在改成：
        1. 查出当前 file_list
        2. 移除目标 file_id
        3. 写回去
        """
        session = self.get_session(session_id)
        if session is None or not session.file_list:
            return 0

        current_list = session.file_list
        if file_id not in current_list:
            return 0

        current_list.remove(file_id)
        self.crud.update_document(
            self.collection,
            {"session_id": session_id},
            {"file_list": current_list}
        )
        return 1

    def get_session_files_content(self, session_id: str, file_id: Optional[str] = None) -> List[Dict]:
        session = self.get_session(session_id)
        if not session or not session.file_list:
            return []

        if file_id:
            if file_id not in session.file_list:
                return []
            target_ids = [file_id]
        else:
            target_ids = session.file_list

        # 原来用 MongoDB 的 $in，CRUD 已经支持了
        files_data = self.crud.find_documents(
            "files",
            {"file_id": {"$in": target_ids}}
        )
        return files_data

    # --- 记忆的集成管理 ---

    def append_chat_message(self, session_id: str, role: str, content: str):
        return self.memory_service.save_memory(session_id, role, content)

    # --- 综合查询 ---

    def get_full_context(self, session_id: str, last_n: int = 10) -> Dict:
        history = self.memory_service.get_recent_memories(session_id, last_n)
        files = self.get_session_files_content(session_id)
        return {
            "history": history,
            "files": files
        }

    # --- 彻底销毁 ---

    def delete_everything_about_session(self, session_id: str):
        self.memory_service.delete_memories_by_session(session_id)
        deleted_count = self.crud.delete_document(self.collection, {"session_id": session_id})
        return deleted_count
