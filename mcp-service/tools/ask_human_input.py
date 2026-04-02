# -*- coding: utf-8 -*-
import json
import uuid
from typing import Optional, List, Dict, Any

from core.decorators import register_tool


@register_tool(
    category="user_interaction",
    description="向用户提问并挂起流程，等待用户输入（HITL）",
)
async def ask_human_input(
    question: str,
    input_type: str = "text",
    expected_input: Optional[List[str]] = None,
    expected_schema: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 300,
    interaction_id: str = "",
    app_id: str = "",
) -> str:
    """
    触发 Human-in-the-loop 交互。

    说明：
    - 该工具不会在 MCP 层阻塞等待用户输入；
    - 它会返回标准挂起指令，主应用解析后将会话标记为 suspended；
    - 用户输入通过恢复接口提交后，主应用继续执行工作流。
    """
    if not question or not question.strip():
        return "问题不能为空"

    input_type = (input_type or "text").strip().lower()
    if input_type not in {"text", "approval", "structured"}:
        return "input_type 仅支持: text / approval / structured"

    if timeout_seconds <= 0:
        return "timeout_seconds 必须大于 0"

    iid = interaction_id.strip() if interaction_id else uuid.uuid4().hex

    payload = {
        "type": "HITL_REQUEST",
        "interaction_id": iid,
        "question": question.strip(),
        "input_type": input_type,
        "expected_input": expected_input or [],
        "expected_schema": expected_schema or {},
        "timeout_seconds": int(timeout_seconds),
        "app_id": app_id or "",
    }

    # 约定前缀，供主应用 generic_tool_runner 快速识别
    return "__HITL__" + json.dumps(payload, ensure_ascii=False)
