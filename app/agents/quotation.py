from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pathlib import Path
from app.core.llm import get_model
from app.tools.factory import load_skill_as_tool

def create_agent_node(llm, tools, system_prompt):
    """创建一个 Agent 节点"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages"),
    ])
    # 绑定工具
    agent = prompt | llm.bind_tools(tools)
    return agent


_ROOT = Path(__file__).resolve().parents[2]
_CALCULATE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "calculate_skill"))
_READ_FILE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "readFile_skill"))

def quotation_node(state):
    llm = get_model(model_choice="high")
    agent = create_agent_node(
        llm,
        [_CALCULATE_TOOL, _READ_FILE_TOOL],
        "你是一名报价计算员，负责根据客户需求计算报价。读取报价单文件，然后根据客户需求计算报价。",
    )
    # 调用并返回结果
    response = agent.invoke(state)
    return {
        "messages": [response],
        "session_id": state.get("session_id", "default"),
    }