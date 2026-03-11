from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # add_messages 表示新消息会追加到历史中
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # 记录下一个要执行的 Agent 名字
    next: str