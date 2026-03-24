# -*- coding: utf-8 -*-
import json
from typing import Optional, List, Dict
from datetime import datetime
from .database import Database
from .CRUD import CRUD
from .Schema import FileModel, MemoryModel, FileTypeModel, SessionModel


class FileService:
    def __init__(self):
        self.crud = CRUD(Database.get_session)
        self.collection = "files"

    def get_file_info(self, file_id: str) -> Optional[Dict]:
        # 直接用主键查询
        return self.crud.find_one(self.collection, {"_id": file_id})

    def save_file_info(self, file_info: FileModel) -> str:
        # 用 file_id 作为主键，主键冲突时直接返回
        doc = file_info.model_dump(by_alias=True, exclude_none=True, exclude={'id'})
        doc["_id"] = file_info.file_id  # 显式设置主键为 MD5

        # 先查询是否存在
        if hit := self.get_file_info(file_info.file_id):
            return hit["_id"]

        return self.crud.insert_document(self.collection, doc)

    def update_file_info(self, file_id: str, update_data: FileModel) -> int:
        # 用主键更新
        data = update_data.model_dump(exclude_none=True, exclude={'id', 'file_id'})
        return self.crud.update_document(self.collection, {"_id": file_id}, data)

    def delete_file_info(self, file_id: str) -> int:
        # 用主键删除
        return self.crud.delete_document(self.collection, {"_id": file_id})


class MemoryService:
    def __init__(self):
        self.crud = CRUD(Database.get_session)
        self.collection = "memories"

    def save_memory(self, session_id: str, role: str, content: str):
        doc = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
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

    def get_session(self, session_id: str) -> Optional[SessionModel]:
        data = self.crud.find_one(self.collection, {"session_id": session_id})
        return SessionModel(**data) if data else None

    def add_file_to_session(self, session_id: str, file_info: FileModel):
        self.file_service.save_file_info(file_info)
        session = self.get_session(session_id)

        if session is None:
            doc = {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "file_list": [file_info.file_id]
            }
            self.crud.insert_document(self.collection, doc)
        else:
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

        # 用主键批量查询（更快）
        files_data = self.crud.find_documents(
            "files",
            {"_id": {"$in": target_ids}}
        )
        return files_data

    def append_chat_message(self, session_id: str, role: str, content: str):
        return self.memory_service.save_memory(session_id, role, content)

    def get_full_context(self, session_id: str, last_n: int = 10) -> Dict:
        history = self.memory_service.get_recent_memories(session_id, last_n)
        files = self.get_session_files_content(session_id)
        return {
            "history": history,
            "files": files
        }

    def delete_everything_about_session(self, session_id: str):
        self.memory_service.delete_memories_by_session(session_id)
        deleted_count = self.crud.delete_document(self.collection, {"session_id": session_id})
        return deleted_count
