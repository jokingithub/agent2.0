# -*- coding: utf-8 -*-
"""
兼容转发壳（deprecated）:
旧路径: app.agents.generic
新路径: app.agents.utils.agent_creator / app.agents.utils.agent_runner
"""

from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig

from app.core.state import AgentState
from app.agents.utils.agent_creator import create_agent_from_config
from app.agents.utils.agent_runner import run_agent
from logger import logger


_WARNED = False


def _warn_once() -> None:
    global _WARNED
    if _WARNED:
        return
    logger.warning(
        "[DEPRECATED] `app.agents.generic` 已迁移，请改用 "
        "`app.agents.utils.agent_creator` / `app.agents.utils.agent_runner`"
    )
    _WARNED = True


# ---- 旧接口兼容：如果外部还在 import generic_agent_node，就转到 run_agent ----
async def generic_agent_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    _warn_once()
    return await run_agent(state, config)


# ---- 旧接口兼容：创建 Agent 的调用 ----
def create_generic_agent(sub_agent_id: str):
    _warn_once()
    return create_agent_from_config(sub_agent_id)


# ---- 常见别名兼容（按需保留）----
build_agent_from_config = create_generic_agent


__all__ = [
    "generic_agent_node",
    "create_generic_agent",
    "build_agent_from_config",
    "create_agent_from_config",
]
