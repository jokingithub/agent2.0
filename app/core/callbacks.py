# -*- coding: utf-8 -*-

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from langchain_core.callbacks import BaseCallbackHandler

from logger import logger


class UsageCollector(BaseCallbackHandler):
    """
    收集每次 LLM 调用的 token + 模型 + agent(node)
    """

    def __init__(self) -> None:
        super().__init__()
        self.total_tokens: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.cached_tokens: int = 0
        self.cache_hit_calls: int = 0
        self.first_token_time: Optional[datetime] = None

        self.call_details: list[dict[str, Any]] = []
        self._seq: int = 0
        self._current_model: str = "unknown"
        self._current_agent: str = "unknown"

        self.error_count: int = 0
        self.last_error: str = ""

    def on_llm_start(self, serialized, prompts=None, *, invocation_params=None, **kwargs):
        if self.first_token_time is None:
            self.first_token_time = datetime.now(timezone.utc)

        self._seq += 1

        model_name = None
        if invocation_params:
            model_name = invocation_params.get("model") or invocation_params.get("model_name")
        if not model_name and serialized and isinstance(serialized, dict):
            kw = serialized.get("kwargs", {}) or {}
            model_name = kw.get("model") or kw.get("model_name")
        self._current_model = model_name or "unknown"

        metadata = kwargs.get("metadata", {}) or {}
        self._current_agent = metadata.get("langgraph_node", "unknown")

    def _extract_cached_tokens(self, usage: Dict[str, Any]) -> int:
        if not isinstance(usage, dict):
            return 0

        ptd = usage.get("prompt_tokens_details") or {}
        v = ptd.get("cached_tokens")
        if isinstance(v, int):
            return v

        for key in ("cached_tokens", "cache_read_tokens", "cache_read"):
            val = usage.get(key)
            if isinstance(val, int):
                return val

        itd = usage.get("input_token_details") or {}
        for key in ("cache_read", "cached_tokens", "cache_read_tokens"):
            val = itd.get(key)
            if isinstance(val, int):
                return val

        return 0

    def _normalize_usage(self, usage: Dict[str, Any]) -> Tuple[int, int, int]:
        """把不同协议的 usage 字段归一成 (prompt, completion, total)"""
        if not isinstance(usage, dict):
            return 0, 0, 0

        prompt = (
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or usage.get("prompt_token_count")
            or 0
        )
        completion = (
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or usage.get("candidates_token_count")
            or 0
        )
        total = (
            usage.get("total_tokens")
            or usage.get("total_token_count")
            or 0
        )

        try:
            prompt = int(prompt or 0)
        except Exception:
            prompt = 0
        try:
            completion = int(completion or 0)
        except Exception:
            completion = 0
        try:
            total = int(total or 0)
        except Exception:
            total = 0

        if total <= 0:
            total = prompt + completion

        return prompt, completion, total

    def on_llm_end(self, response, **kwargs):
        call_prompt = 0
        call_completion = 0
        call_total = 0
        call_cached = 0

        # 1) llm_output
        try:
            if response and hasattr(response, "llm_output") and response.llm_output:
                usage = response.llm_output.get("token_usage") or response.llm_output.get("usage") or {}
                p, c, t = self._normalize_usage(usage)
                call_prompt += p
                call_completion += c
                call_total += t
                call_cached += self._extract_cached_tokens(usage)
        except Exception:
            pass

        # 2) generations[*][*].message metadata
        try:
            if response and hasattr(response, "generations"):
                for gen_list in response.generations or []:
                    for gen in gen_list or []:
                        msg = getattr(gen, "message", None)
                        if not msg:
                            continue

                        usage_meta = getattr(msg, "usage_metadata", None) or {}
                        p, c, t = self._normalize_usage(usage_meta)
                        call_prompt += p
                        call_completion += c
                        call_total += t
                        call_cached += self._extract_cached_tokens(usage_meta)

                        resp_meta = getattr(msg, "response_metadata", None) or {}
                        for u in (resp_meta.get("token_usage") or {}, resp_meta.get("usage") or {}):
                            p2, c2, t2 = self._normalize_usage(u)
                            call_prompt += p2
                            call_completion += c2
                            call_total += t2
                            call_cached += self._extract_cached_tokens(u)
        except Exception:
            pass

        if call_total <= 0:
            call_total = call_prompt + call_completion

        cache_hit = call_cached > 0
        self.cached_tokens += call_cached
        if cache_hit:
            self.cache_hit_calls += 1

        self.total_tokens += call_total
        self.prompt_tokens += call_prompt
        self.completion_tokens += call_completion

        self.call_details.append(
            {
                "seq": self._seq,
                "agent": self._current_agent,
                "model": self._current_model,
                "prompt_tokens": call_prompt,
                "completion_tokens": call_completion,
                "total_tokens": call_total,
                "cached_tokens": call_cached,
                "cache_hit": cache_hit,
            }
        )

    def on_llm_error(self, error, **kwargs):
        self.error_count += 1
        self.last_error = str(error)
        logger.error(
            f"[TOKEN][ERROR] seq={self._seq} agent={self._current_agent} model={self._current_model} err={error}"
        )

    @property
    def final_model(self) -> Optional[str]:
        if not self.call_details:
            return None
        return self.call_details[-1].get("model")

    @property
    def final_agent(self) -> Optional[str]:
        if not self.call_details:
            return None
        return self.call_details[-1].get("agent")
