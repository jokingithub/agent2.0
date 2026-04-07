# app/core/state.py
# -*- coding: utf-8 -*-

from typing import Annotated, Sequence, TypedDict, Optional, List, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # 路由键：Supervisor 只返回 RUN_AGENT / FINISH
    next: str

    # 当前要执行的 sub_agent 名称（运行时动态）
    current_agent: Optional[str]

    # Supervisor 拆解后的子任务指令，注入给 SubAgent
    sub_task_instruction: Optional[str]

    # 当前生效角色名（给前端展示）
    role_name: Optional[str]
    selected_role_id: Optional[str]

    session_id: str
    app_id: str
    scene_id: str

    role_config: Optional[Dict[str, Any]]
    available_sub_agents: Optional[List[str]]
    session_files: Optional[List[Dict[str, Any]]]

    # HITL 挂起信息
    user_input_required: Optional[bool]
    suspended_action: Optional[str]
    pending_context: Optional[Dict[str, Any]]
