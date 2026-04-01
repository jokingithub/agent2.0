# -*- coding: utf-8 -*-
# 文件：fileUpload/element_extraction.py
# 配置驱动的要素抽取，从 file_processing 表读取字段和提示词

import json
import re
from app.core.llm import get_model_by_level_id
from dataBase.ConfigService import (
    FileProcessingService,
    ElementExtractionModelConfigService,
    ModelLevelService,
)
from logger import logger

_fp_service = FileProcessingService()
_ee_model_cfg_service = ElementExtractionModelConfigService()
_model_level_service = ModelLevelService()

_DEFAULT_PROMPT_TEMPLATE = """# Role
你是一个专业的数据抽取专家，擅长从各类文档中精确提取关键信息。

# Task
请从【原始文本】中提取以下字段，严格按 JSON 格式返回。

# 需要提取的字段
{fields_desc}

# 约束
1. 返回纯 JSON，不要包裹在 markdown 代码块中。
2. 所有内容必须来自原文，严禁捏造。
3. 未提及的字段设为 null。
4. 保持数值的原始精度。"""


def _parse_json_response(text: str, expected_fields: list[str] | None = None) -> dict:
    """从 LLM 回复中提取 JSON"""
    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 提取 ```json ... ``` 块
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # 提取第一个 { ... }
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    # 兜底：解析“字段：值”列表（如 markdown 条目）
    parsed: dict[str, str | None] = {}
    lines = text.splitlines()
    kv_patterns = [
        re.compile(r'^\s*[*\-•]?\s*\*\*?\s*([^：:\n]+?)\s*\*\*?\s*[：:]\s*(.*?)\s*$'),
        re.compile(r'^\s*[*\-•]?\s*([^：:\n]+?)\s*[：:]\s*(.*?)\s*$'),
    ]
    for line in lines:
        for pat in kv_patterns:
            m = pat.match(line)
            if not m:
                continue
            key = (m.group(1) or "").strip().strip("*` ")
            val = (m.group(2) or "").strip()
            if not key:
                continue
            parsed[key] = val if val else None
            break

    if parsed:
        if expected_fields:
            normalized_map = {
                re.sub(r"\s+", "", f).replace("：", ":").strip(" :"): f
                for f in expected_fields
            }
            out: dict[str, str | None] = {f: None for f in expected_fields}
            for k, v in parsed.items():
                nk = re.sub(r"\s+", "", k).replace("：", ":").strip(" :")
                target = normalized_map.get(nk)
                if target:
                    out[target] = v
            if any(v is not None for v in out.values()):
                return out
        return parsed

    logger.error(f"无法解析 LLM 返回的 JSON: {text[:200]}")
    return {"_parse_error": True, "_raw": text[:500]}


def _find_config(file_type: str) -> dict | None:
    """查配置，支持精确匹配和模糊匹配"""
    # 精确匹配
    config = _fp_service.get_by_file_type(file_type)
    if config:
        return config

    # 模糊匹配：AI分类可能返回"履约保函"，配置表里是"保函"
    all_configs = _fp_service.get_all()
    for c in all_configs:
        ct = c.get("file_type", "")
        if ct in file_type or file_type in ct:
            logger.info(f"模糊匹配: '{file_type}' → '{ct}'")
            return c

    return None


def _get_element_extraction_model():
    """读取要素抽取模型配置，仅支持 model_id。"""
    cfg = _ee_model_cfg_service.get_current() or {}

    model_id = (cfg.get("model_id") or cfg.get("model_level_id") or "").strip()

    if not model_id:
        logger.error("要素抽取未配置 model_id，已跳过抽取")
        return None

    level = _model_level_service.get_by_id(model_id)
    if not level:
        logger.error(f"要素抽取配置的 model_id 无效: {model_id}，已跳过抽取")
        return None

    logger.info(f"要素抽取使用模型(model_id): {model_id}")
    return get_model_by_level_id(model_id)


def element_extraction(file_content: str, file_type: str) -> dict:
    """
    根据 file_processing 配置表抽取要素。
    file_type: AI分类结果，如 "保函"、"合同"（可能是列表中的某一项）
    """
    logger.info(f"要素抽取 - 文件类型: {file_type}")

    # 1. 查配置表
    config = _find_config(file_type)

    if not config:
        logger.warning(f"file_processing 表无 '{file_type}' 配置，跳过抽取")
        return {}

    fields = config.get("fields", [])
    if not fields:
        logger.warning(f"'{file_type}' 配置的 fields 为空，跳过抽取")
        return {}

    # 2. 构造 prompt
    custom_prompt = config.get("prompt")
    if custom_prompt:
        system_prompt = custom_prompt
    else:
        fields_desc = "\n".join([f"- {f}" for f in fields])
        system_prompt = _DEFAULT_PROMPT_TEMPLATE.format(fields_desc=fields_desc)

    # 3. 调用 LLM
    model = _get_element_extraction_model()
    if model is None:
        logger.error("要素抽取模型不可用，跳过抽取")
        return {}
    messages = [
        ("system", system_prompt),
        ("user", f"请从以下文本中提取要素：\n\n{file_content}")
    ]

    try:
        response = model.invoke(messages)
        result = _parse_json_response(response.content, expected_fields=fields)
        logger.info(f"要素抽取完成: {list(result.keys())}")
        return result
    except Exception as e:
        logger.error(f"要素抽取异常: {e}", exc_info=True)
        return {"_error": str(e)}
