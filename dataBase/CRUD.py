# dataBase/CRUD.py

from .database import Database
from bson import ObjectId

class CRUD:
    def __init__(self, db):
        self.db = db

    def _convert_id(self, doc):
        """格式化文档，将 ObjectId 转换为字符串"""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    def insert_document(self, collection_name: str, document: dict) -> str:
        collection = self.db[collection_name]
        result = collection.insert_one(document) # 使用 insert_one
        return str(result.inserted_id)

    def find_documents(self, collection_name: str, query: dict) -> list[dict]:
        collection = self.db[collection_name]
        # 加上 list 转换，并处理 ID
        return [self._convert_id(doc) for doc in collection.find(query)]

    def find_one(self, collection_name: str, query: dict) -> dict:
        collection = self.db[collection_name]
        return self._convert_id(collection.find_one(query))
    
    def update_document(self, collection_name: str, query: dict, update: dict) -> int:
        """根据查询条件更新文档，返回修改的文档数量"""
        collection = self.db[collection_name]
        result = collection.update_many(query, {"$set": update})
        return result.modified_count

    def delete_document(self, collection_name: str, query: dict) -> int:
        """根据查询条件删除文档，返回删除的文档数量"""
        collection = self.db[collection_name]
        result = collection.delete_many(query)
        return result.deleted_count