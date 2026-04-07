# app/core/state.py
# -*- coding: utf-8 -*-

from typing import Annotated, Sequence, TypedDict, Optional, List, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    next: str
    current_agent: Optional[str]
    role_name: Optional[str]
    selected_role_id: Optional[str]

    session_id: str
    app_id: str
    scene_id: str

    role_config: Optional[Dict[str, Any]]
    available_sub_agents: Optional[List[str]]
    session_files: Optional[List[Dict[str, Any]]]

    # 新增：Supervisor 下发给 subagent 的任务指令
    sub_task_instruction: Optional[str]

    # 新增：subagent 私有工作区（不要给 Supervisor/其他agent复用）
    agent_scratchpad: Optional[List[BaseMessage]]

    user_input_required: Optional[bool]
    suspended_action: Optional[str]
    pending_context: Optional[Dict[str, Any]]