# -*- coding: utf-8 -*-
# 文件：app/core/state.py
# time: 2026/3/9

from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # add_messages 表示新消息会追加到历史中
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # 记录下一个要执行的 Agent 名字
    next: str
    # 当前会话 ID（用于隔离会话级资源）
    session_id: str