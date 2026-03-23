# -*- coding: utf-8 -*-
# 文件：config.py
# time: 2026/3/19

import os
from dotenv import load_dotenv

# 加载 .env 文件中的变量
load_dotenv()

class Config:
    # MongoDB 配置
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "agent_db")

    # PG 配置
    PG_URI = os.getenv("PG_URI", "postgresql://agent:agent123@localhost:5432/agent")

    # OpenAI API 配置
    OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    # langfuse 相关配置
    LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3301")
    
    # 还可以加其他配置
    DEBUG = os.getenv("DEBUG", "False") == "True"

    # 日志配置
    # 日志配置
    LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO")
    LOG_TO_CONSOLE=os.getenv("LOG_TO_CONSOLE", "True") == "True"
    LOG_FILE_PATH=os.getenv("LOG_FILE_PATH", "logs/app.log")
    LOG_MAX_BYTES=int(os.getenv("LOG_MAX_BYTES", 10*1024*1024))  # 默认10MB
    LOG_BACKUP_COUNT=int(os.getenv("LOG_BACKUP_COUNT", 5))  # 默认保留5个旧文件