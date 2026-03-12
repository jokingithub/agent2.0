from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage
from pathlib import Path
from app.core.state import AgentState
from app.core.agents_config import AGENT_REGISTRY
from app.agents.quotation import quotation_node
from app.agents.supervisor import supervisor_node
from app.agents.reviewer import reviewer_node
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
    workflow.add_node("reviewer", reviewer_node)

    # 后续扩展：在这里补充新 agent 对应 node 函数
    node_impl_map = {
        "quotation": quotation_node,
    }
    
    # # 技能执行节点（LangGraph 提供的工具自动执行节点）
    workflow.add_node("call_calculate_tool", ToolNode([_READ_FILE_TOOL,_CALCULATE_TOOL]))
    workflow.add_node("call_read_file_tool", ToolNode([_READ_FILE_TOOL]))

    # 2. 建立连线 (Edges)
    # Researcher 执行完后，如果需要调工具则去 tool 节点，否则回主管
    workflow.add_edge("call_calculate_tool", "quotation")
    workflow.add_edge("call_read_file_tool", "reviewer")

    # 3. 条件路由
    supervisor_routes = {name: name for name in AGENT_REGISTRY.keys()}
    supervisor_routes["FINISH"] = END
    workflow.add_conditional_edges("Supervisor", lambda x: x["next"], supervisor_routes)

    # quotation 输出如果包含 tool_calls，则执行工具，再回 quotation 生成最终回答
    workflow.add_conditional_edges(
        "quotation",
        route_after_quotation,
        {
            "tool": "call_calculate_tool",
            "done": END,
        },
    )

    workflow.add_conditional_edges(
        "reviewer",
        route_after_quotation,
        {
            "tool": "call_read_file_tool",
            "done": END,
        },
    )

    workflow.set_entry_point("Supervisor")
    return workflow.compile()