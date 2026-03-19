# -*- coding: utf-8 -*-
# 文件：dataBase/database.py
# time: 2026/3/19

from pymongo import MongoClient
from logger import logger
# 如果 config.py 在根目录
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

class Database:
    client = None
    db = None

    @classmethod
    def connect(cls, uri=None, db_name=None):
        # 如果没传参，默认从 Config 拿
        uri = uri or Config.MONGO_URI
        db_name = db_name or Config.MONGO_DB_NAME
        
        try:
            # 增加连接超时设置，防止程序卡死
            cls.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            
            # 强制检查连接是否可用
            cls.client.admin.command('ping') 
            
            cls.db = cls.client[db_name]
            logger.info(f"Successfully connected to MongoDB: {db_name}",exc_info=True)
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}", exc_info=True)
            raise e

    @classmethod
    def get_db(cls):
        if cls.db is None:
            # 自动尝试连接一次，或者抛出异常
            cls.connect()
        return cls.db