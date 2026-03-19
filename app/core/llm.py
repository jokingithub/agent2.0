# -*- coding: utf-8 -*-
# 文件：app/core/llm.py
# time: 2026/3/9

from langchain_openai import ChatOpenAI
import os
from pathlib import Path
from config import Config
from logger import logger

def get_model(model_choice: str = "high") -> ChatOpenAI:
    api_key = Config.OPENAI_API_KEY
    if not api_key:
        logger.error("未读取到 OPENAI_API_KEY，请在环境变量或 .env 文件中配置。")
    model = {
        "high": "google/gemini-3-flash-preview",
        "medium": "google/gemini-2.5-pro-preview",
        "low": "google/gemini-1.5-pro-preview",
    }
    return ChatOpenAI(
        model=model.get(model_choice, "google/gemini-3-flash-preview"),
        temperature=0,
        api_key=api_key,
        base_url=Config.OPENAI_API_BASE_URL,
    )