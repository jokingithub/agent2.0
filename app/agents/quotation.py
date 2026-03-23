"""报价Agent - 优先从配置表读，兜底用硬编码"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pathlib import Path
from app.core.llm import get_model
from app.tools.factory import load_skill_as_tool
from dataBase.ConfigService import SubAgentService
from app.agents.generic import create_agent_from_config
from logger import logger

_sub_agent_service = SubAgentService()
_ROOT = Path(__file__).resolve().parents[2]

# 本地工具兜底
_CALCULATE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "calculate_skill"))
_READ_FILE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "readFile_skill"))


def _find_sub_agent_id(name: str):
    """从sub_agents表按name查找ID"""
    try:
        agents = _sub_agent_service.get_all()
        for a in agents:
            if a.get("name") == name:
                return a.get("_id")
    except:
        pass
    return None


def quotation_node(state):
    # 优先从配置表创建
    agent_id = _find_sub_agent_id("quotation")
    if agent_id:
        result = create_agent_from_config(agent_id)
        if result:
            agent, tools = result
            response = agent.invoke(state)
            return {
                "messages": [response],
                "session_id": state.get("session_id", "default"),
            }

    # 兜底：硬编码
    #raise RuntimeError("quotation 配置表未找到，兜底已禁用！请检查 sub_agents 表")
    logger.warning("quotation 使用硬编码兜底")
    llm = get_model("high")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一名报价计算员，负责根据客户需求计算报价。"),
        MessagesPlaceholder(variable_name="messages"),
    ])
    agent = prompt | llm.bind_tools([_CALCULATE_TOOL, _READ_FILE_TOOL])
    response = agent.invoke(state)
    return {
        "messages": [response],
        "session_id": state.get("session_id", "default"),
    }
