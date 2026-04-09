# app/prompts/__init__.py
# -*- coding: utf-8 -*-
"""提示词统一管理入口"""

from app.prompts.supervisor import (
    SUPERVISOR_SYSTEM_PROMPT,
    SUPERVISOR_DEFAULT_SYSTEM_PROMPT,
)
from app.prompts.sub_agent import (
    SUB_TASK_INJECTION_TEMPLATE,
    FILE_LIST_TEMPLATE,
)

__all__ = [
    "SUPERVISOR_SYSTEM_PROMPT",
    "SUPERVISOR_DEFAULT_SYSTEM_PROMPT",
    "SUB_TASK_INJECTION_TEMPLATE",
    "FILE_LIST_TEMPLATE",
]
