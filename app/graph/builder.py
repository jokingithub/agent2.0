# -*- coding: utf-8 -*-
# 文件：app/graph/builder.py

from typing import Set, List, Dict
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage

from app.core.state import AgentState
from app.core.agents_config import AGENT_REGISTRY
from app.agents.quotation import quotation_node
from app.agents.supervisor import supervisor_node
from app.agents.reviewer import reviewer_node
from app.agents.generic import generic_agent_node
from app.tools.factory import load_skill_as_tool
from dataBase.ConfigService import SubAgentService, RoleService, SceneService
from logger import logger

_ROOT = Path(__file__).resolve().parents[2]
_CALCULATE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "calculate_skill"))
_READ_FILE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "readFile_skill"))

_sub_agent_service = SubAgentService()
_role_service = RoleService()
_scene_service = SceneService()

# 硬编码节点映射（兜底）
_HARDCODED_NODES = {
    "quotation": quotation_node,
    "reviewer": reviewer_node,
}


def route_after_quotation(state: AgentState) -> str:
    """报价/审核节点后路由：有 tool_calls 则执行工具，否则结束。"""
    messages = state.get("messages", [])
    if not messages:
        return "done"

    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tool"
    return "done"


def route_after_agent(state: AgentState) -> str:
    """通用 sub_agent 路由：有 tool_calls 则执行工具，否则结束。"""
    messages = state.get("messages", [])
    if not messages:
        return "done"

    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tool"
    return "done"


def _log_startup_topology(registered_names: Set[str]) -> None:
    """
    启动时打印两层拓扑：
    1) 物理图节点（LangGraph编译节点）
    2) 业务路由图（scene -> role -> sub_agents）
    """
    try:
        roles = _role_service.get_all() or []
        scenes = _scene_service.get_all() or []
        sub_agents = _sub_agent_service.get_all() or []

        role_by_id: Dict[str, dict] = {
            r.get("_id"): r for r in roles if r.get("_id")
        }
        sub_name_by_id: Dict[str, str] = {
            s.get("_id"): s.get("name", "") for s in sub_agents if s.get("_id")
        }

        logger.info("========== Graph Topology (Startup) ==========")

        # A) 物理节点（编译节点）
        physical_nodes = sorted(
            list(
                set(registered_names)
                | {"Supervisor", "call_calculate_tool", "call_read_file_tool", "call_generic_tools"}
            )
        )
        logger.info(f"[Physical Nodes] {physical_nodes}")
        logger.info("[Physical Edge] ENTRY -> Supervisor")

        if "quotation" in registered_names:
            logger.info("[Physical Edge] quotation --(tool_calls?)--> call_calculate_tool -> quotation | END")
        if "reviewer" in registered_names:
            logger.info("[Physical Edge] reviewer --(tool_calls?)--> call_read_file_tool -> reviewer | END")

        generic_agents: List[str] = [n for n in sorted(registered_names) if n not in ("quotation", "reviewer")]
        if generic_agents:
            logger.info(f"[Physical Edge] {generic_agents} --(tool_calls?)--> call_generic_tools -> 当前agent | END")

        # B) 业务路由（scene -> role -> sub_agents）
        if not scenes:
            logger.info("[Business Route] scenes 为空")
        else:
            for sc in scenes:
                scene_code = sc.get("scene_code", "")
                role_ids = sc.get("available_role_ids", []) or []

                if not role_ids:
                    logger.info(f"[Business Route] scene='{scene_code}' -> (no role)")
                    continue

                # 当前约定：一个 scene 对应一个 role（取第一个）
                role_id = role_ids[0]
                role = role_by_id.get(role_id)
                if not role:
                    logger.info(f"[Business Route] scene='{scene_code}' -> role_id='{role_id}' (missing)")
                    continue

                role_name = role.get("name", "unknown")
                sub_agent_ids = role.get("sub_agent_ids", []) or []
                sub_agent_names = [sub_name_by_id.get(sid, f"<missing:{sid}>") for sid in sub_agent_ids]

                logger.info(
                    f"[Business Route] scene='{scene_code}' -> role='{role_name}' -> "
                    f"sub_agents={sub_agent_names} + ['FINISH']"
                )

                # 如果 scene 配了多个 role，额外提示（不参与当前运行）
                if len(role_ids) > 1:
                    extra = role_ids[1:]
                    logger.info(
                        f"[Business Route][WARN] scene='{scene_code}' 存在多个role_ids，当前仅使用第一个；"
                        f"extra_role_ids={extra}"
                    )

        logger.info("========== End Graph Topology ==========")

    except Exception as e:
        logger.warning(f"打印启动拓扑失败: {e}")


def create_graph():
    workflow = StateGraph(AgentState)

    # ============================================================
    # 1. 固定节点
    # ============================================================
    workflow.add_node("Supervisor", supervisor_node)

    # ============================================================
    # 2. 从 sub_agents 表动态注册节点
    # ============================================================
    registered_names: Set[str] = set()

    try:
        all_sub_agents = _sub_agent_service.get_all()
        if all_sub_agents:
            for sa in all_sub_agents:
                name = sa.get("name", "")
                agent_id = sa.get("_id", "")
                if not name or not agent_id:
                    continue

                # 如果有同名硬编码节点，优先用硬编码
                if name in _HARDCODED_NODES:
                    logger.info(f"graph: '{name}' 使用硬编码节点（保留特殊逻辑）")
                    workflow.add_node(name, _HARDCODED_NODES[name])
                else:
                    logger.info(f"graph: '{name}' 使用配置驱动节点 (id={agent_id})")
                    workflow.add_node(name, generic_agent_node(agent_id))

                registered_names.add(name)

            logger.info(f"graph: 从配置表注册了 {len(registered_names)} 个 sub_agent 节点: {registered_names}")
    except Exception as e:
        logger.warning(f"graph: 从配置表加载 sub_agents 失败: {e}，使用硬编码兜底")

    # ============================================================
    # 3. 硬编码兜底：配置表里没有的，补上
    # ============================================================
    for name, node_fn in _HARDCODED_NODES.items():
        if name not in registered_names:
            logger.info(f"graph: '{name}' 兜底注册（配置表中不存在）")
            workflow.add_node(name, node_fn)
            registered_names.add(name)

    # AGENT_REGISTRY 仅用于提示，不注册空节点
    for name in AGENT_REGISTRY:
        if name not in registered_names:
            logger.info(f"graph: '{name}' 从 AGENT_REGISTRY 兜底注册（跳过空实现）")
            pass

    # ============================================================
    # 4. 工具节点
    # ============================================================
    workflow.add_node("call_calculate_tool", ToolNode([_READ_FILE_TOOL, _CALCULATE_TOOL]))
    workflow.add_node("call_read_file_tool", ToolNode([_READ_FILE_TOOL]))
    workflow.add_node("call_generic_tools", ToolNode([_READ_FILE_TOOL, _CALCULATE_TOOL]))

    # ============================================================
    # 5. 条件路由
    # ============================================================
    # Supervisor -> 任意已注册节点 或 FINISH
    supervisor_routes = {name: name for name in registered_names}
    supervisor_routes["FINISH"] = END
    workflow.add_conditional_edges("Supervisor", lambda x: x["next"], supervisor_routes)

    # ============================================================
    # 6. 各 sub_agent 的出边
    # ============================================================
    # quotation: 特殊逻辑
    if "quotation" in registered_names:
        workflow.add_conditional_edges(
            "quotation",
            route_after_quotation,
            {"tool": "call_calculate_tool", "done": END},
        )
        workflow.add_edge("call_calculate_tool", "quotation")

    # reviewer: 特殊逻辑
    if "reviewer" in registered_names:
        workflow.add_conditional_edges(
            "reviewer",
            route_after_quotation,
            {"tool": "call_read_file_tool", "done": END},
        )
        workflow.add_edge("call_read_file_tool", "reviewer")

    # 其他通用节点
    generic_agents = [n for n in registered_names if n not in ("quotation", "reviewer")]
    generic_agent_set = set(generic_agents)

    for name in generic_agents:
        workflow.add_conditional_edges(
            name,
            route_after_agent,
            {"tool": "call_generic_tools", "done": END},
        )

    # call_generic_tools 执行后，只回到“当前agent”（state.next）
    def route_back_from_generic_tool(state: AgentState) -> str:
        nxt = state.get("next", "")
        if nxt in generic_agent_set:
            return nxt
        return "FINISH"

    if generic_agents:
        back_routes = {name: name for name in generic_agents}
        back_routes["FINISH"] = END
        workflow.add_conditional_edges("call_generic_tools", route_back_from_generic_tool, back_routes)

    # ============================================================
    # 7. 入口
    # ============================================================
    workflow.set_entry_point("Supervisor")

    compiled = workflow.compile()
    logger.info(f"graph: 编译完成，节点={list(registered_names | {'Supervisor'})}")

    # 启动时输出“物理图 + 业务路由图”
    _log_startup_topology(registered_names)

    return compiled
