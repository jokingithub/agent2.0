from __future__ import annotations

import json
from typing import Any

from langchain_openai import ChatOpenAI

from Schema import LLMConfig
from utils.errors import FileProcessError


class LlmClient:
    """统一LLM调用客户端。"""

    def __init__(self, llm_config: LLMConfig) -> None:
        self.model = ChatOpenAI(
            model=llm_config.model,
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            temperature=llm_config.temperature,
            timeout=llm_config.timeout,
        )

    def invoke_text(self, prompt: str) -> str:
        response = self.model.invoke([("user", prompt)])
        content = getattr(response, "content", "")
        return str(content).strip()

    def invoke_json(self, prompt: str) -> dict[str, Any]:
        text = self.invoke_text(prompt)
        try:
            return json.loads(self._clean_json_text(text))
        except Exception as exc:
            raise FileProcessError(f"LLM返回JSON解析失败: {text[:300]}") from exc

    def _clean_json_text(self, text: str) -> str:
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        return text.strip()
