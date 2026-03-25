# -*- coding: utf-8 -*-
# 文件：config.py
# time: 2026/3/19

import os
from dotenv import load_dotenv

# 加载 .env 文件中的变量
load_dotenv()


def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

class Config:
    # MongoDB 配置
    # MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    # MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "agent_db")

    # PG 配置
    PG_URI = os.getenv("PG_URI", "postgresql://agent:agent123@localhost:5432/agent")

    # OpenAI API 配置
    OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    # langfuse 相关配置
    LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3301")

    # OCR服务地址（本地默认 127.0.0.1，Docker 内默认 host.docker.internal）
    _DEFAULT_OCR_SERVICE_URL = (
        "http://host.docker.internal:8001"
        if os.path.exists("/.dockerenv")
        else "http://127.0.0.1:8001"
    )
    OCR_SERVICE_URL = os.getenv("OCR_SERVICE_URL", _DEFAULT_OCR_SERVICE_URL)
    
    # 运行环境：debug / production
    APP_ENV = os.getenv("APP_ENV", "debug").strip().lower()
    IS_PRODUCTION = APP_ENV in {"prod", "production"}

    # 兼容旧配置，未显式传入 DEBUG 时由 APP_ENV 推导
    DEBUG = _to_bool(os.getenv("DEBUG"), default=not IS_PRODUCTION)

    # FastAPI 文档页开关（生产默认关闭）
    ENABLE_API_DOCS = _to_bool(
        os.getenv("ENABLE_API_DOCS"),
        default=not IS_PRODUCTION,
    )

    # 日志配置
    # 日志配置
    LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO")
    LOG_TO_CONSOLE=os.getenv("LOG_TO_CONSOLE", "True") == "True"
    LOG_FILE_PATH=os.getenv("LOG_FILE_PATH", "logs/app.log")
    LOG_MAX_BYTES=int(os.getenv("LOG_MAX_BYTES", 10*1024*1024))  # 默认10MB
    LOG_BACKUP_COUNT=int(os.getenv("LOG_BACKUP_COUNT", 5))  # 默认保留5个旧文件