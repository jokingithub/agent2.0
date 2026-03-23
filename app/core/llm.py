# -*- coding: utf-8 -*-
#文件：app/core/llm.py

from langchain_openai import ChatOpenAI
from config import Config
from logger import logger
from dataBase.ConfigService import ModelLevelService, ModelConnectionService

_model_level_service = ModelLevelService()
_model_connection_service = ModelConnectionService()

#硬编码兜底，配置表没数据时用
_FALLBACK = {
    "base_url": Config.OPENAI_API_BASE_URL,
    "api_key": Config.OPENAI_API_KEY,
    "model_map": {
        "high": "google/gemini-3-flash-preview",
        "medium": "google/gemini-2.5-pro-preview",
        "low": "google/gemini-1.5-pro-preview",
        "test": "qwen3.5-35b-a3b",
    },
}


def get_model(model_choice: str = "high") -> ChatOpenAI:
    """
    优先从配置表读模型，失败则用硬编码兜底。
    model_choice 支持两种用法：
      - 传tier 名称："high" / "medium" / "low" / "test"
      - 传 model_level_id：直接指定某条model_levels 记录
    """
    result = _try_from_config(model_choice)
    if result:
        return result

    # 兜底
    #raise RuntimeError(f"配置表未找到模型 '{model_choice}'，兜底已禁用！请检查 model_levels 表")
    logger.warning(f"配置表未找到模型 '{model_choice}'，使用硬编码兜底")
    return ChatOpenAI(
        model=_FALLBACK["model_map"].get(model_choice, _FALLBACK["model_map"]["high"]),
        temperature=0,
        api_key=_FALLBACK["api_key"],
        base_url=_FALLBACK["base_url"],
    )


def get_model_by_level_id(level_id: str) -> ChatOpenAI:
    """
    直接通过 model_level 的 ID 获取模型。
    用于 sub_agent 配置中的 model_id 字段。
    """
    result = _build_from_level_id(level_id)
    if result:
        return result

    logger.warning(f"model_level_id '{level_id}' 未找到，使用默认 high 模型")
    return get_model("high")


def _try_from_config(model_choice: str) -> ChatOpenAI | None:
    """尝试从配置表获取模型"""
    try:
        # 方式1：model_choice 是 tier 名称（如 "high"）
        # 从model_levels 表按 name匹配
        levels = _model_level_service.get_all()
        if not levels:
            return None

        # 按 name 匹配
        target = None
        for lv in levels:
            if lv.get("name") == model_choice:
                target = lv
                break

        # 如果 name 没匹配到，尝试当作 ID
        if not target:
            target = _model_level_service.get_by_id(model_choice)

        if not target:
            return None

        return _build_from_level(target)

    except Exception as e:
        logger.warning(f"从配置表读模型失败: {e}")
        return None


def _build_from_level_id(level_id: str) -> ChatOpenAI | None:
    """通过 level ID 构建模型"""
    try:
        level = _model_level_service.get_by_id(level_id)
        if not level:
            return None
        return _build_from_level(level)
    except Exception as e:
        logger.warning(f"构建模型失败 (level_id={level_id}): {e}")
        return None


def _build_from_level(level: dict) -> ChatOpenAI | None:
    """从 model_level 记录 + 关联的 model_connection 构建 ChatOpenAI"""
    connection_id = level.get("connection_id")
    model_name = level.get("model")
    timeout = level.get("timeout", 30)

    if not connection_id or not model_name:
        logger.warning(f"model_level 缺少 connection_id 或 model: {level}")
        return None

    connection = _model_connection_service.get_by_id(connection_id)
    if not connection:
        logger.warning(f"model_connection '{connection_id}' 不存在")
        return None

    base_url = connection.get("base_url")
    api_key = connection.get("api_key")

    if not base_url or not api_key:
        logger.warning(f"model_connection 缺少 base_url 或 api_key: {connection}")
        return None

    return ChatOpenAI(
        model=model_name,
        temperature=0,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )
