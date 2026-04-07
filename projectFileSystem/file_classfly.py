from __future__ import annotations

from Schema import FileTypeConfig, LLMConfig
from services.llm_client import LlmClient

def classify_file_by_config(
    content: str,
    filename: str,
    file_configs: list[FileTypeConfig],
    llm_config: LLMConfig,
) -> str:
    """基于LLM进行文件分类，返回单一类型。"""
    enabled = [cfg for cfg in file_configs if cfg.available]
    if not enabled:
        return "其他"

    type_names = [cfg.file_type for cfg in enabled]
    prompt = _build_classify_prompt(filename=filename, content=content, type_names=type_names)
    result = LlmClient(llm_config).invoke_text(prompt)
    cleaned = result.replace("，", ",").split(",")[0].strip()
    return cleaned if cleaned in type_names else "其他"


def _build_classify_prompt(filename: str, content: str, type_names: list[str]) -> str:
    candidate = "、".join(type_names)
    return (
        "你是文件分类助手。请从候选类型中选择最匹配的一项。\n"
        f"候选类型：{candidate}\n"
        "输出要求：仅输出一个候选类型名称；若都不匹配输出'其他'。\n"
        f"文件名：{filename}\n"
        f"文件内容（截断）：\n{content[:5000]}"
    )
