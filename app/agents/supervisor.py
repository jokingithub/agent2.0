"""Supervisor - 从roles表读配置，从sub_agents表读路由"""

from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage
from app.core.llm import get_model, get_model_by_level_id
from app.core.agents_config import AGENT_REGISTRY, ROUTABLE_NEXT
from dataBase.ConfigService import RoleService, SubAgentService
from logger import logger

_role_service = RoleService()
_sub_agent_service = SubAgentService()


class SupervisorDecision(BaseModel):
    next: str = Field(description="下一步路由")
    reason: str = Field(default="", description="路由原因")


class SimpleAnswerCheck(BaseModel):
    is_simple: bool = Field(description="是否是简单问答")
    answer: str = Field(default="", description="直接答案")


def _load_supervisor_config():
    """从roles表读supervisor配置"""
    try:
        roles = _role_service.get_all()
        for r in roles:
            # 找名为supervisor或主角色的记录
            if r.get("name") in ("supervisor", "主管", "Supervisor"):
                return r
    except Exception as e:
        logger.warning(f"读取supervisor配置失败: {e}")
        return None


def _load_available_agents():
    """从sub_agents表读可路由的Agent列表"""
    try:
        agents = _sub_agent_service.get_all()
        if agents:
            result = {}
            for a in agents:
                name = a.get("name", "")
                desc = a.get("description") or a.get("system_prompt", "")[:50]
                if name:
                    result[name] = desc
            if result:
                return result
    except Exception as e:
        logger.warning(f"读取sub_agents失败: {e}")

    # 兜底
    return AGENT_REGISTRY


def supervisor_node(state):
    # 从配置表读
    config = _load_supervisor_config()
    available_subagents = _load_available_agents()
    routable = tuple(list(available_subagents.keys()) + ["FINISH"])

    # 读模型
    if config and config.get("main_model_id"):
        llm_base = get_model_by_level_id(config["main_model_id"])
    else:
        llm_base = get_model("high")

    # 读提示词
    if config and config.get("system_prompt"):
        system_prompt = config["system_prompt"]
    else:
        system_prompt = "你是团队主管。请根据对话进度，在可用subagent 中选择下一步。如果任务已完成，返回 FINISH。"
        #raise RuntimeError("supervisor 配置表未找到，兜底已禁用！请检查 roles 表")

    # --- 以下逻辑和现在一样 ---

    messages = state.get("messages", [])

    # 快速终止
    if messages:
        last = messages[-1]
        if isinstance(last, AIMessage):
            has_tools = bool(getattr(last, "tool_calls", None))
            content = (last.content or "") if isinstance(last.content, str) else str(last.content or "")
            if (not has_tools) and content.strip():
                return {"next": "FINISH", "session_id": state.get("session_id", "default")}

    # 简单问答检测
    if messages:
        check_prompt = (
            "判断用户的最后一个问题是否是'简单问答'。\n"
            "简单问答的定义：不需要专门的客服、报价、审核等领域能力，"
            "可以通过通用知识或常识直接回答的问题。\n"
            "如果是简单问答，直接提供答案。如果不是，返回空答案。"
        )
        llm_check = llm_base.with_structured_output(SimpleAnswerCheck)
        check_result = llm_check.invoke([("system", check_prompt), *messages])

        if check_result.is_simple and check_result.answer.strip():
            return {
                "messages": [AIMessage(content=check_result.answer)],
                "next": "FINISH",
                "session_id": state.get("session_id", "default"),
            }

    # 路由决策
    llm_decision = llm_base.with_structured_output(SupervisorDecision)
    decision = llm_decision.invoke([
        ("system", f"{system_prompt}\n可用 subagent: {available_subagents}\n只允许在{list(routable)} 中选择 next。"),
        *messages,
    ])

    next_node = decision.next if decision.next in routable else "FINISH"
    return {"next": next_node, "session_id": state.get("session_id", "default")}
