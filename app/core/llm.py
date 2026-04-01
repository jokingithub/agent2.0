# -*- coding: utf-8 -*-
# 文件：app/core/llm.py

from typing import Optional, Tuple, Dict, Any
from langchain_openai import ChatOpenAI

from config import Config
from logger import logger
from dataBase.ConfigService import ModelLevelService, ModelConnectionService

_model_level_service = ModelLevelService()
_model_connection_service = ModelConnectionService()

# 硬编码兜底，配置表没数据时用
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
    兼容旧接口：只返回 llm
    """
    llm, _ = get_model_with_meta(model_choice)
    return llm


def get_model_by_level_id(level_id: str) -> ChatOpenAI:
    """
    兼容旧接口：只返回 llm
    """
    llm, _ = get_model_by_level_id_with_meta(level_id)
    return llm


def get_model_with_meta(model_choice: str = "high") -> Tuple[ChatOpenAI, Dict[str, Any]]:
    """
    新接口：返回 (llm, meta)
    meta 可用于日志追踪每次调用的模型信息
    """
    result = _try_from_config_with_meta(model_choice)
    if result:
        return result

    # 兜底
    fallback_model = _fallback_model_name(model_choice)
    logger.warning(f"配置表未找到模型 '{model_choice}'，使用硬编码兜底: {fallback_model}")

    llm = ChatOpenAI(
        model=fallback_model,
        temperature=0,
        api_key=_FALLBACK["api_key"],
        base_url=_FALLBACK["base_url"],
        streaming=True,
    )

    meta = {
        "model": fallback_model,
        "source": "fallback",
        "level_id": "",
        "level_name": model_choice,
        "level": None,
        "connection_id": "",
        "protocol": "",
        "base_url": _FALLBACK["base_url"],
    }
    return llm, meta


def get_model_by_level_id_with_meta(level_id: str) -> Tuple[ChatOpenAI, Dict[str, Any]]:
    """
    新接口：通过 model_level_id 获取 (llm, meta)
    用于 sub_agent 配置中的 model_id 字段
    """
    result = _build_from_level_id_with_meta(level_id)
    if result:
        return result

    logger.warning(f"model_level_id '{level_id}' 未找到，使用默认 high 模型")
    llm, meta = get_model_with_meta("high")
    meta["requested_level_id"] = level_id
    return llm, meta


# ---------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------

def _fallback_model_name(model_choice: str) -> str:
    return _FALLBACK["model_map"].get(model_choice, _FALLBACK["model_map"]["high"])


def _try_from_config(model_choice: str) -> Optional[ChatOpenAI]:
    """
    兼容旧内部函数：只返回 llm
    """
    result = _try_from_config_with_meta(model_choice)
    return result[0] if result else None


def _try_from_config_with_meta(model_choice: str) -> Optional[Tuple[ChatOpenAI, Dict[str, Any]]]:
    """
    尝试从配置表获取模型（按 name 或 id）
    """
    try:
        levels = _model_level_service.get_all()
        if not levels:
            return None

        # 1) 按 name 匹配（如 high / medium）
        target = None
        for lv in levels:
            if lv.get("name") == model_choice:
                target = lv
                break

        # 2) name 没匹配到，尝试当作 level_id
        if not target:
            target = _model_level_service.get_by_id(model_choice)

        if not target:
            return None

        return _build_from_level_with_meta(target)

    except Exception as e:
        logger.warning(f"从配置表读模型失败: {e}")
        return None


def _build_from_level_id(level_id: str) -> Optional[ChatOpenAI]:
    """
    兼容旧内部函数：只返回 llm
    """
    result = _build_from_level_id_with_meta(level_id)
    return result[0] if result else None


def _build_from_level_id_with_meta(level_id: str) -> Optional[Tuple[ChatOpenAI, Dict[str, Any]]]:
    """
    通过 level_id 构建 (llm, meta)
    """
    try:
        level = _model_level_service.get_by_id(level_id)
        if not level:
            return None
        return _build_from_level_with_meta(level)
    except Exception as e:
        logger.warning(f"构建模型失败 (level_id={level_id}): {e}")
        return None


def _build_from_level(level: dict) -> Optional[ChatOpenAI]:
    """
    兼容旧内部函数：只返回 llm
    """
    result = _build_from_level_with_meta(level)
    return result[0] if result else None


def _build_from_level_with_meta(level: dict) -> Optional[Tuple[ChatOpenAI, Dict[str, Any]]]:
    """
    从 model_level + model_connection 构建 (llm, meta)
    """
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
    protocol = connection.get("protocol", "")

    if not base_url or not api_key:
        logger.warning(f"model_connection 缺少 base_url 或 api_key: {connection}")
        return None

    llm = ChatOpenAI(
        model=model_name,
        temperature=0,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        streaming=True,
    )

    meta = {
        "model": model_name,
        "source": "config",
        "level_id": str(level.get("_id", level.get("id", ""))),
        "level_name": level.get("name", ""),
        "level": level.get("level"),
        "connection_id": connection_id,
        "protocol": protocol,
        "base_url": base_url,
    }

    return llm, meta
