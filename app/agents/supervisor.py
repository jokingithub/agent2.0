from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

from app.core.llm import get_model
from app.core.agents_config import AGENT_REGISTRY, ROUTABLE_NEXT


class SupervisorDecision(BaseModel):
    next: str = Field(
        description="下一步路由，必须是可用 subagent 名称或 FINISH"
    )
    reason: str = Field(default="", description="路由原因")

def supervisor_node(state):
    available_subagents = AGENT_REGISTRY

    system_prompt = (
        "你是团队主管。请根据对话进度，在可用 subagent 中选择下一步。"
        "如果任务已完成，返回 FINISH。"
    )

    # 快速终止条件：已有可用最终答案时直接结束
    messages = state.get("messages", [])
    if messages:
        last = messages[-1]
        if isinstance(last, AIMessage):
            has_tools = bool(getattr(last, "tool_calls", None))
            content = (last.content or "") if isinstance(last.content, str) else str(last.content or "")
            if (not has_tools) and content.strip():
                return {
                    "next": "FINISH",
                    "session_id": state.get("session_id", "default"),
                }

    llm = get_model(model_choice="high").with_structured_output(SupervisorDecision)
    decision = llm.invoke(
        [
            (
                "system",
                (
                    f"{system_prompt}\n"
                    f"可用 subagent: {available_subagents}\n"
                    f"只允许在 {list(ROUTABLE_NEXT)} 中选择 next。"
                ),
            ),
            *state.get("messages", []),
        ]
    )

    next_node = decision.next if decision.next in ROUTABLE_NEXT else "FINISH"

    return {
        "next": next_node,
        "session_id": state.get("session_id", "default"),
    }