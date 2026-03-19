# -*- coding: utf-8 -*-
from typing import List, Dict, Any, Optional

class CRUD:
    def __init__(self, db):
        self.db = db

    def _convert_id(self, doc: Optional[Dict]):
        """将 ObjectId 转换为字符串，方便前端和 JSON 处理"""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    def insert_document(self, collection_name: str, document: Dict) -> str:
        # 如果包含 _id 且为 None，则删除，让 MongoDB 自动生成
        if "_id" in document and document["_id"] is None:
            document.pop("_id")
        result = self.db[collection_name].insert_one(document)
        return str(result.inserted_id)

    def find_one(self, collection_name: str, query: Dict) -> Optional[Dict]:
        doc = self.db[collection_name].find_one(query)
        return self._convert_id(doc)

    def find_documents(self, 
                       collection_name: str, 
                       query: Dict, 
                       sort_by: str = None, 
                       ascending: bool = True, 
                       limit: int = 0) -> List[Dict]:
        """封装了排序和限制的查询"""
        cursor = self.db[collection_name].find(query)
        if sort_by:
            cursor = cursor.sort(sort_by, 1 if ascending else -1)
        if limit > 0:
            cursor = cursor.limit(limit)
        
        return [self._convert_id(doc) for doc in cursor]

    def update_document(self, collection_name: str, query: Dict, update_data: Dict, upsert: bool = False) -> int:
        # 防止更新 _id 导致报错
        if "_id" in update_data:
            update_data.pop("_id")
        
        result = self.db[collection_name].update_many(
            query, 
            {"$set": update_data}, 
            upsert=upsert
        )
        return result.modified_count

    def delete_document(self, collection_name: str, query: Dict) -> int:
        result = self.db[collection_name].delete_many(query)
        return result.deleted_count