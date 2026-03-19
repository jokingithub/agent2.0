# -*- coding: utf-8 -*-
from typing import Optional, List, Dict
from datetime import datetime
from .database import Database
from .CRUD import CRUD
from .Schema import FileModel, MemoryModel, FileTypeModel, SessionModel

class FileService:
    def __init__(self):
        self.crud = CRUD(Database.get_db())
        self.collection = "files"

    def get_file_info(self, file_id: str) -> Optional[Dict]:
        return self.crud.find_one(self.collection, {"file_id": file_id})

    def save_file_info(self, file_info: FileModel) -> str:
        """保存或获取已存在文件的ID"""
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
        self.crud = CRUD(Database.get_db())
        self.collection = "memories"

    def save_memory(self, session_id: str, role: str, content: str):
        doc = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        }
        return self.crud.insert_document(self.collection, doc)

    def get_recent_memories(self, session_id: str, last_n: int = 10) -> List[Dict]:
        """获取最近 n 条记录，并按时间正序排列（AI上下文需要）"""
        # 先取倒序最后 n 条
        mems = self.crud.find_documents(
            self.collection, 
            {"session_id": session_id}, 
            sort_by="timestamp", 
            ascending=False, 
            limit=last_n
        )
        # 翻转回正序
        return mems[::-1]

    def delete_memories_by_session(self, session_id: str) -> int:
        return self.crud.delete_document(self.collection, {"session_id": session_id})


class FileTypeService:
    def __init__(self):
        self.crud = CRUD(Database.get_db())
        self.collection = "config"

    def update_file_types(self, model: FileTypeModel):
        self.crud.update_document(
            self.collection, 
            {"_id": "global_file_types"}, 
            model.model_dump(), 
            upsert=True
        )

    def get_file_types(self) -> List[str]:
        doc = self.crud.find_one(self.collection, {"_id": "global_file_types"})
        return doc.get("file_type", []) if doc else []


class SessionService:
    def __init__(self):
        # 初始化时获取数据库连接
        self.db = Database.get_db()
        self.crud = CRUD(self.db)
        self.collection = "sessions"
        # 内部组合其他服务，实现级联操作
        self.memory_service = MemoryService()
        self.file_service = FileService()

    def get_session(self, session_id: str) -> Optional[SessionModel]:
        """获取会话模型对象"""
        data = self.crud.find_one(self.collection, {"session_id": session_id})
        return SessionModel(**data) if data else None

    # --- 文件的集成管理 ---

    def add_file_to_session(self, session_id: str, file_info: FileModel):
        """
        全自动化：保存/更新文件实体 + 将文件ID关联到会话
        """
        # 1. 调用 FileService 确保文件已经存在于 files 集合中
        # 这里会返回插入的 ID 或已存在的 ID，但我们通常在 file_list 存业务 file_id
        self.file_service.save_file_info(file_info)
        
        # 2. 将 file_id 记录在 Session 的 file_list 列表中
        # 使用 $addToSet 确保不会重复添加同一个文件 ID
        # 使用 upsert=True 确保如果会话文档不存在则自动创建
        self.db[self.collection].update_one(
            {"session_id": session_id},
            {
                "$addToSet": {"file_list": file_info.file_id},
                "$setOnInsert": {"created_at": datetime.now()}
            },
            upsert=True
        )
        return file_info.file_id

    def remove_file_from_session(self, session_id: str, file_id: str) -> int:
        """
        从会话中移除某个文件的关联 (仅断开关联，不删除文件实体)
        """
        result = self.db[self.collection].update_one(
            {"session_id": session_id},
            {"$pull": {"file_list": file_id}}
        )
        return result.modified_count

    def get_session_files_content(self, session_id: str, file_id: Optional[str] = None) -> List[Dict]:
        """
        获取某个会话关联的所有文件的详细内容或者单个文件内容
        用于给 AI 喂数据
        """
        session = self.get_session(session_id)
        if not session or not session.file_list:
            return []
        
        # 确定要查询的范围：是指定文件还是全部文件
        if file_id:
            # 如果指定了 file_id，先验证它是否在当前会话的列表中
            if file_id not in session.file_list:
                return []
            target_ids = [file_id]
        else:
            target_ids = session.file_list
        
        # 批量从 files 集合查询详情
        files_data = self.crud.find_documents(
            "files", 
            {"file_id": {"$in": target_ids}}
        )
        return files_data

    # --- 2. 记忆的集成管理 ---

    def append_chat_message(self, session_id: str, role: str, content: str):
        """一键存储对话记录"""
        return self.memory_service.save_memory(session_id, role, content)

    # --- 3. 综合查询 ---

    def get_full_context(self, session_id: str, last_n: int = 10) -> Dict:
        """
        AI 助手最核心的方法：
        一次性拿到：最近聊天记录 (正序) + 该会话关联的所有文件详情
        """
        history = self.memory_service.get_recent_memories(session_id, last_n)
        files = self.get_session_files_content(session_id)
        
        return {
            "history": history,
            "files": files
        }

    # --- 4. 彻底销毁 ---

    def delete_everything_about_session(self, session_id: str):
        """
        级联删除：删除会话所有记忆、删除会话记录本身
        注意：通常不删除关联的文件实体，因为文件可能被其他会话复用
        """
        # 1. 删除所有对话记忆
        self.memory_service.delete_memories_by_session(session_id)
        
        # 2. 删除会话本身
        deleted_count = self.crud.delete_document(self.collection, {"session_id": session_id})
        return deleted_count