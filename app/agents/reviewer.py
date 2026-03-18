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
# _CALCULATE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "calculate_skill"))
_READ_FILE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "readFile_skill"))

rule = """
【审查要点清单】  索赔通知形式：保函条款是否明确规定索赔必须以\"书面通知\"方式提出？（必须包含\"书面\"字样）  独立性确认时效：格式审查流程是否规定大于\"7个工作日\"？  可转让性限制：保函是否包含\"不可转让\"条款？  保函性质明确性：保函正文是否明确其法律性质？必须包含以下任一表述：  标明保证类型：\"一般保证\"或\"连带责任保证\"  表明独立保函性质：\"见索即付\"、\"无条件\"、\"不可撤销\"或\"不争辩\"  生效时间逻辑性：保函生效日期是否不早于开立日期？  索赔条件合理性：保函是否将\"不提交新保函\"作为索赔的触发条件？（此项应为否定审查）  文本一致性：保函中各方主体名称、称谓是否前后完全一致？  有效期完整性：保函是否明确规定了有效期限？  【输出格式要求】 请以清晰列表形式逐条回应，每条格式如下：  审查要点X：[要点简述]  审查结果：通过/未通过/不适用  问题描述：（如未通过，请具体说明问题所在及条款位置）  修改建议：（如未通过，提供具体修改建议）  请对保函条款进行严格审查，确保每个要点都得到明确验证。
"""

def reviewer_node(state):
    llm = get_model(model_choice="high")
    agent = create_agent_node(
        llm,
        # [_CALCULATE_TOOL, _READ_FILE_TOOL],
        [ _READ_FILE_TOOL],
        "你是一个保函审核员，根据一下规则，审核客户提交的保函文件是否符合要求：\n" + rule,
    )
    # 调用并返回结果
    response = agent.invoke(state)
    return {
        "messages": [response],
        "session_id": state.get("session_id", "default"),
    }