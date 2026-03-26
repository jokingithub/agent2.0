# -*- coding: utf-8 -*-
# 文件：app/core/state.py

from typing import Annotated, Sequence, TypedDict, Optional, List, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # add_messages 表示新消息会追加到历史中
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # 记录下一个要执行的 Agent 名字
    next: str
    # 当前会话 ID
    session_id: str
    # 应用隔离
    app_id: str
    # 场景码
    scene_id: str
    # 当前生效的 role 配置（supervisor 填入，sub_agent 可读）
    role_config: Optional[Dict[str, Any]]
    # 当前 role 下可路由的 sub_agent 名称列表
    available_sub_agents: Optional[List[str]]
