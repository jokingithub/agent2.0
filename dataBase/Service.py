# -*- coding: utf-8 -*-
# 文件：dataBase/Service.py
# time: 2026/3/19

from .database import Database
from .CRUD import CRUD
from .Schema import FileModel, MemoryModel, FileTypeModel

class FileService:
    def __init__(self):
        self.crud = CRUD(Database.get_db())
        self.collection = "files"

    def save_file_info(self, file_info: FileModel):
        doc = file_info.model_dump(by_alias=True, exclude_none=True)
        new_id = self.crud.insert_document(self.collection, doc)
        return new_id

    def get_file_info(self, file_id: str):
        data = self.crud.find_one(self.collection, {"file_id": file_id})
        return data
    
    def update_file_info(self, file_id: str, update_data: FileModel):
        modified_count = self.crud.update_document(self.collection, {"file_id": file_id}, update_data)
        return modified_count
    
    def delete_file_info(self, file_id: str):
        deleted_count = self.crud.delete_document(self.collection, {"file_id": file_id})
        return deleted_count
    
class MemoryService:
    def __init__(self):
        self.crud = CRUD(Database.get_db())
        self.collection = "memories"

    def save_memory(self, memory_info: MemoryModel):
        doc = memory_info.model_dump(by_alias=True, exclude_none=True)
        new_id = self.crud.insert_document(self.collection, doc)
        return new_id

    def get_memories_by_session(self, session_id: str):
        data = self.crud.find_documents(self.collection, {"session_id": session_id})
        return data
    
    def delete_memories_by_session(self, session_id: str):
        deleted_count = self.crud.delete_document(self.collection, {"session_id": session_id})
        return deleted_count
    
class FileTypeService:
    def __init__(self):
        self.crud = CRUD(Database.get_db())
        self.collection = "file_types" # 建议专门存配置的集合

    def update_file_types(self, model: FileTypeModel):
        # 使用 upsert=True：如果数据库没数据，就新增；有数据，就更新
        # 我们假设数据库里只存一条 ID 为 "global_types" 的配置
        self.crud.db[self.collection].update_one(
            {"_id": "global_types"},
            {"$set": {"file_type": model.file_type}},
            upsert=True  # 关键点！
        )

    def get_file_types(self) -> list:
        # 查找那条全局配置
        doc = self.crud.db[self.collection].find_one({"_id": "global_types"})
        if doc and "file_type" in doc:
            return doc["file_type"]
        return []