from __future__ import annotations

from typing import Any

from Schema import FileTypeConfig, LLMConfig
from services.llm_client import LlmClient


def extract_elements_by_config(
	content: str,
	file_type_config: FileTypeConfig | None,
	llm_config: LLMConfig,
) -> dict[str, Any]:
	"""按配置定义使用LLM抽取要素，返回JSON对象。"""
	if not file_type_config:
		return {}

	keys = [item.element_key for item in file_type_config.elements]
	schema_lines = [f"- {item.element_key}: {item.description}" for item in file_type_config.elements]
	prompt = _build_extract_prompt(content=content, schema_lines=schema_lines)
	parsed = LlmClient(llm_config).invoke_json(prompt)
	return {k: parsed.get(k) for k in keys}


def _build_extract_prompt(content: str, schema_lines: list[str]) -> str:
	schema_text = "\n".join(schema_lines)
	return (
		"你是文档要素抽取助手。请严格按字段要求抽取信息。\n"
		"返回要求：仅返回JSON对象，不要输出解释。\n"
		"字段说明：\n"
		f"{schema_text}\n"
		"若字段不存在请返回 null。\n"
		f"文档内容（截断）：\n{content[:7000]}"
	)
