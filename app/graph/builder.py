from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage
from pathlib import Path
from app.core.state import AgentState
from app.agents.quotation import quotation_node
from app.agents.supervisor import supervisor_node
# from app.skills.search_skill import web_search_tool
from app.tools.factory import load_skill_as_tool


_ROOT = Path(__file__).resolve().parents[2]
_CALCULATE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "calculate_skill"))
_READ_FILE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "readFile_skill"))


def route_after_quotation(state: AgentState) -> str:
    """报价节点后路由：有 tool_calls 则执行工具，否则结束。"""
    messages = state.get("messages", [])
    if not messages:
        return "done"

    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tool"
    return "done"

def create_graph():
    workflow = StateGraph(AgentState)

    # 1. 添加节点
    workflow.add_node("quotation", quotation_node)
    workflow.add_node("Supervisor", supervisor_node)
    
    # # 技能执行节点（LangGraph 提供的工具自动执行节点）
    workflow.add_node("call_tools", ToolNode([_CALCULATE_TOOL, _READ_FILE_TOOL]))

    # 2. 建立连线 (Edges)
    # Researcher 执行完后，如果需要调工具则去 tool 节点，否则回主管
    workflow.add_edge("call_tools", "quotation")

    # 3. 条件路由
    workflow.add_conditional_edges(
        "Supervisor",
        lambda x: x["next"],
        {
            "quotation": "quotation",
            "FINISH": END
        }
    )

    # quotation 输出如果包含 tool_calls，则执行工具，再回 quotation 生成最终回答
    workflow.add_conditional_edges(
        "quotation",
        route_after_quotation,
        {
            "tool": "call_tools",
            "done": END,
        },
    )

    workflow.set_entry_point("Supervisor")
    return workflow.compile()