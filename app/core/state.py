# app/core/state.py
# -*- coding: utf-8 -*-

from typing import Annotated, Sequence, TypedDict, Optional, List, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # 路由键：Supervisor 只返回 RUN_AGENT / FINISH
    next: str
    next_action: Optional[str]

    # 当前要执行的 sub_agent 名称（运行时动态）
    current_agent: Optional[str]
    current_actor: Optional[str]

    # 当前生效角色名（给前端展示）
    role_name: Optional[str]
    selected_role_id: Optional[str]  # ← 新增：前端指定的 role

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

    # HITL 恢复模式标记（仅恢复入口首轮使用）
    resume_mode: Optional[bool]

    # ReAct 循环控制
    react_step: Optional[int]
    max_steps: Optional[int]

    # ReAct 轨迹信息
    last_action: Optional[Dict[str, Any]]
    last_observation: Optional[Dict[str, Any]]
    trace: Optional[List[Dict[str, Any]]]
