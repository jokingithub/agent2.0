# -*- coding: utf-8 -*-
from pymongo import MongoClient, ASCENDING, DESCENDING
from logger import logger
from config import Config

class Database:
    _client = None
    _db = None

    @classmethod
    def connect(cls):
        if cls._client is None:
            try:
                cls._client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
                cls._client.admin.command('ping')
                cls._db = cls._client[Config.MONGO_DB_NAME]
                
                cls._init_indices()
                
                logger.info(f"Connected to MongoDB and indices initialized.")
            except Exception as e:
                logger.error(f"MongoDB Connection Error: {e}")
                raise e

    @classmethod
    def _init_indices(cls):
        """初始化各个集合的索引"""
        try:
            # 1. 为 files 集合的 file_id 建立唯一索引
            cls._db["files"].create_index([("file_id", ASCENDING)], unique=True)

            # 2. 为 sessions 集合的 session_id 建立唯一索引
            cls._db["sessions"].create_index([("session_id", ASCENDING)], unique=True)

            # 3. 为 memories 集合建立复合索引
            # 因为你经常根据 session_id 查询并按 timestamp 排序，复合索引效率最高
            cls._db["memories"].create_index([
                ("session_id", ASCENDING), 
                ("timestamp", DESCENDING)
            ])
            
            logger.info("MongoDB indices ensured.")
        except Exception as e:
            logger.warning(f"Could not create indices: {e}")

    @classmethod
    def get_db(cls):
        if cls._db is None:
            cls.connect()
        return cls._db