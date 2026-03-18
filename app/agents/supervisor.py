from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, HumanMessage

from app.core.llm import get_model
from app.core.agents_config import AGENT_REGISTRY, ROUTABLE_NEXT


class SupervisorDecision(BaseModel):
    next: str = Field(
        description="下一步路由，必须是可用 subagent 名称或 FINISH"
    )
    reason: str = Field(default="", description="路由原因")


class SimpleAnswerCheck(BaseModel):
    is_simple: bool = Field(description="是否是简单问答，可以直接回答")
    answer: str = Field(default="", description="如果是简单问答，直接提供答案")


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

    # 简单问答检测：判断是否可以直接回答，无需路由给其他 Agent
    if messages:
        check_prompt = (
            "判断用户的最后一个问题是否是'简单问答'。\n"
            "简单问答的定义：不需要专门的客服、报价、审核等领域能力，"
            "可以通过通用知识或常识直接回答的问题。\n"
            "如果是简单问答，直接提供答案。如果不是，返回空答案。"
        )
        
        llm = get_model(model_choice="high").with_structured_output(SimpleAnswerCheck)
        check_result = llm.invoke(
            [
                ("system", check_prompt),
                *messages,
            ]
        )
        
        if check_result.is_simple and check_result.answer.strip():
            # 简单问答：直接生成答案并结束
            return {
                "messages": [AIMessage(content=check_result.answer)],
                "next": "FINISH",
                "session_id": state.get("session_id", "default"),
            }

    # 复杂问题：需要路由到专门 Agent
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