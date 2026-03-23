"""通用Agent工厂 - 从配置表动态创建Agent节点"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.core.llm import get_model, get_model_by_level_id
from app.tools.factory import load_tools_for_sub_agent, load_skill_as_tool
from dataBase.ConfigService import SubAgentService
from pathlib import Path
from logger import logger

_sub_agent_service = SubAgentService()
_ROOT = Path(__file__).resolve().parents[2]

# 本地skills缓存（保留现有的本地技能）
_LOCAL_SKILLS = {}

def _get_local_skill(skill_name: str):
    """加载本地skill目录的工具"""
    if skill_name not in _LOCAL_SKILLS:
        skill_dir = _ROOT / "app" / "skills" / skill_name
        if skill_dir.exists():
            try:
                _LOCAL_SKILLS[skill_name] = load_skill_as_tool(str(skill_dir))
            except Exception as e:
                logger.warning(f"加载本地skill '{skill_name}' 失败: {e}")
                return None
    return _LOCAL_SKILLS.get(skill_name)


def create_agent_from_config(sub_agent_id: str):
    """
    从sub_agents表读配置，动态创建Agent。
    返回一个可调用的agent chain。
    """
    config = _sub_agent_service.get_by_id(sub_agent_id)
    if not config:
        logger.warning(f"sub_agent '{sub_agent_id}' 不存在")
        return None

    # 1. 读模型
    model_id = config.get("model_id")
    if model_id:
        llm = get_model_by_level_id(model_id)
    else:
        llm = get_model("high")

    # 2. 读工具（配置表里的工具）
    tools = load_tools_for_sub_agent(sub_agent_id)

    # 3. 读提示词
    system_prompt = config.get("system_prompt", "你是一个AI助手。")

    # 4. 构建agent
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages"),
    ])

    if tools:
        agent = prompt | llm.bind_tools(tools)
    else:
        agent = prompt | llm

    return agent, tools


def generic_agent_node(sub_agent_id: str):
    """
    返回一个node函数，供graph调用。
    闭包捕获sub_agent_id。
    """
    def node_fn(state):
        result = create_agent_from_config(sub_agent_id)
        if result is None:
            #兜底：直接返回错误信息
            from langchain_core.messages import AIMessage
            return {
                "messages": [AIMessage(content=f"Agent '{sub_agent_id}' 配置不存在")],
                "session_id": state.get("session_id", "default"),
            }

        agent, tools = result
        response = agent.invoke(state)
        return {
            "messages": [response],
            "session_id": state.get("session_id", "default"),
        }

    return node_fn
