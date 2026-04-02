# -*- coding: utf-8 -*-
"""统一 Generic Runner（无须为每个 sub_agent 注册图节点）"""

import json
from typing import Optional, Dict, Any, List
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode

from dataBase.ConfigService import SubAgentService
from app.agents.generic import create_agent_from_config
from app.tools.factory import load_tools_for_sub_agent, load_tools_for_role
from app.core.state import AgentState
from logger import logger
from dataBase.ConfigService import RoleService

_sub_agent_service = SubAgentService()
_role_service = RoleService()


def _build_session_files_context(session_files: List[Dict[str, Any]]) -> str:
    """把会话文件及 main_info 压缩为可读上下文。"""
    if not session_files:
        return ""

    lines: List[str] = ["当前会话关联的文件与已提取关键信息（请优先复用，不要遗漏已确认字段）："]
    for idx, f in enumerate(session_files, start=1):
        file_name = f.get("file_name", "unknown")
        file_id = f.get("file_id", "unknown")
        lines.append(f"{idx}. {file_name} (ID: {file_id})")

        main_info = f.get("main_info") or {}
        if isinstance(main_info, dict) and main_info:
            for k, v in main_info.items():
                v_text = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
                v_text = v_text.replace("\n", " ").strip()
                if len(v_text) > 200:
                    v_text = v_text[:200] + "..."
                lines.append(f"   - {k}: {v_text}")
        else:
            lines.append("   - main_info: 无")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n...(文件摘要已截断)"
    return text


def _inject_runtime_app_id(args: Any, app_id: str) -> Any:
    """将运行时 app_id 注入 tool args。

    兼容：
    - args 为 dict（顶层或 data 嵌套）
    - args 为 JSON 字符串
    """
    if not app_id:
        return args

    if isinstance(args, dict):
        # 1) 嵌套 data 注入（兼容 arg_name=data 的工具）
        data = args.get("data")
        if isinstance(data, dict):
            # 强制以运行时 app_id 为准
            data["app_id"] = app_id
            # data 嵌套存在时，不额外注入顶层 app_id，避免下游 schema 校验报多余字段
            args.pop("app_id", None)
            return args

        # 2) 非 data 嵌套场景：顶层强制覆盖注入
        args["app_id"] = app_id
        return args

    if isinstance(args, str):
        text = args.strip()
        if not text:
            return {"app_id": app_id}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                parsed.setdefault("app_id", app_id)
                data = parsed.get("data")
                if isinstance(data, dict):
                    data.setdefault("app_id", app_id)
                return parsed
        except Exception:
            pass
        return {"query": args, "app_id": app_id}

    return {"query": str(args), "app_id": app_id}


def _find_sub_agent_by_name(name: str) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    try:
        all_agents = _sub_agent_service.get_all() or []
        for a in all_agents:
            if a.get("name") == name:
                return a
    except Exception as e:
        logger.warning(f"查找 sub_agent 失败 name={name}, err={e}")
    return None


def route_after_generic_agent(state: AgentState) -> str:
    """GenericAgentRunner 后路由：有 tool_calls -> TOOL，否则 DONE"""
    messages = state.get("messages", [])
    if not messages:
        return "DONE"

    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "TOOL"
    return "DONE"


async def generic_agent_runner(state: AgentState, config: RunnableConfig = None):
    try:
        current_step = int(state.get("react_step") or 0)
    except Exception:
        current_step = 0
    try:
        max_steps = int(state.get("max_steps") or 12)
    except Exception:
        max_steps = 12
    if max_steps <= 0:
        max_steps = 12

    next_step = current_step + 1

    if next_step > max_steps:
        return {
            "messages": [AIMessage(content=f"已达到最大推理步数限制（{max_steps}），本轮停止执行。")],
            "current_agent": (state.get("current_agent") or "").strip(),
            "resume_mode": False,
            "react_step": current_step,
            "max_steps": max_steps,
        }

    current_agent = (state.get("current_agent") or "").strip()
    if not current_agent:
        nxt = (state.get("next") or "").strip()
        if nxt and nxt not in ("RUN_AGENT", "FINISH"):
            current_agent = nxt
    if not current_agent:
        return {
            "messages": [AIMessage(content="未指定 current_agent，无法执行子Agent。")],
            "current_agent": "",
            "resume_mode": False,
            "react_step": next_step,
            "max_steps": max_steps,
        }

    sa = _find_sub_agent_by_name(current_agent)
    if not sa:
        return {
            "messages": [AIMessage(content=f"未找到子Agent配置: {current_agent}")],
            "current_agent": current_agent,
            "resume_mode": False,
            "react_step": next_step,
            "max_steps": max_steps,
        }

    sa_id = sa.get("_id")
    if not sa_id:
        return {
            "messages": [AIMessage(content=f"子Agent配置缺少 _id: {current_agent}")],
            "current_agent": current_agent,
            "resume_mode": False,
            "react_step": next_step,
            "max_steps": max_steps,
        }

    result = create_agent_from_config(sa_id)
    if not result:
        return {
            "messages": [AIMessage(content=f"子Agent创建失败: {current_agent}")],
            "current_agent": current_agent,
            "resume_mode": False,
            "react_step": next_step,
            "max_steps": max_steps,
        }

    agent, tools = result
    session_files = state.get("session_files") or []
    messages = list(state.get("messages", []))
    if session_files and tools:
        file_ctx = _build_session_files_context(session_files)
        if file_ctx:
            messages.insert(0, SystemMessage(content=file_ctx))

    response = await agent.ainvoke({"messages": messages}, config=config)
    return {
        "messages": [response],
        "current_agent": current_agent,
        "resume_mode": False,
        "react_step": next_step,
        "max_steps": max_steps,
    }


async def generic_tool_runner(state: AgentState, config: RunnableConfig):
    messages = state.get("messages", [])
    if not messages:
        return {
            "current_agent": state.get("current_agent", ""),
            "react_step": state.get("react_step", 0),
            "max_steps": state.get("max_steps", 12),
        }

    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) if isinstance(last, AIMessage) else None
    if not tool_calls:
        return {
            "current_agent": state.get("current_agent", ""),
            "react_step": state.get("react_step", 0),
            "max_steps": state.get("max_steps", 12),
        }

    runtime_app_id = (state.get("app_id") or "").strip()
    if runtime_app_id:
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            if "args" in tc:
                tc["args"] = _inject_runtime_app_id(tc.get("args"), runtime_app_id)
            elif "arguments" in tc:
                tc["arguments"] = _inject_runtime_app_id(tc.get("arguments"), runtime_app_id)

    current_actor = (state.get("current_actor") or "").strip()
    current_agent = (state.get("current_agent") or "").strip()
    role_config = state.get("role_config") if isinstance(state.get("role_config"), dict) else None

    tools = []
    if current_actor == "supervisor" or (not current_agent and current_actor in ("", "supervisor")):
        # 主Agent调工具
        if not role_config:
            selected_role_id = (state.get("selected_role_id") or "").strip()
            if selected_role_id:
                try:
                    role_config = _role_service.get_by_id(selected_role_id)
                except Exception:
                    role_config = None
        tools = load_tools_for_role(role_config or {}) or []
        current_actor = "supervisor"
    else:
        # subagent 调工具
        sa = _find_sub_agent_by_name(current_agent) if current_agent else None
        sa_id = sa.get("_id") if sa else None
        if not sa_id:
            err_msgs: List[ToolMessage] = []
            for i, tc in enumerate(tool_calls):
                tcid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if not tcid:
                    tcid = f"toolcall_{i}"
                err_msgs.append(
                    ToolMessage(
                        content=f"工具执行失败：未找到 current_agent='{current_agent}' 对应 sub_agent 配置",
                        tool_call_id=tcid,
                    )
                )
            return {
                "messages": err_msgs,
                "current_agent": current_agent,
                "current_actor": current_actor or current_agent,
                "react_step": state.get("react_step", 0),
                "max_steps": state.get("max_steps", 12),
            }
        tools = load_tools_for_sub_agent(sa_id) or []
        current_actor = current_agent

    if not tools:
        err_msgs: List[ToolMessage] = []
        for i, tc in enumerate(tool_calls):
            tcid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
            if not tcid:
                tcid = f"toolcall_{i}"
            err_msgs.append(
                ToolMessage(
                    content=f"工具执行失败：actor '{current_actor or current_agent or 'supervisor'}' 当前无可用工具",
                    tool_call_id=tcid,
                )
            )
        return {
            "messages": err_msgs,
            "current_agent": current_agent,
            "current_actor": current_actor or current_agent,
            "react_step": state.get("react_step", 0),
            "max_steps": state.get("max_steps", 12),
        }

    node = ToolNode(tools)
    result = await node.ainvoke(state, config=config)

    # HITL 协议识别：工具返回以 __HITL__ 开头的 JSON 字符串
    if isinstance(result, dict):
        out_messages = result.get("messages") or []
        for msg in out_messages:
            if not isinstance(msg, ToolMessage):
                continue
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if not isinstance(content, str) or not content.startswith("__HITL__"):
                continue

            payload_str = content[len("__HITL__"):].strip()
            try:
                payload = json.loads(payload_str) if payload_str else {}
            except Exception:
                payload = {}

            # 兼容兜底字段
            interaction_id = payload.get("interaction_id", "")
            question = payload.get("question", "")
            input_type = payload.get("input_type", "text")
            timeout_seconds = int(payload.get("timeout_seconds", 300) or 300)
            expected_input = payload.get("expected_input") or []
            expected_schema = payload.get("expected_schema") or {}

            result["user_input_required"] = True
            result["suspended_action"] = "hitl_user_input"
            result["pending_context"] = {
                "interaction_id": interaction_id,
                "question": question,
                "input_type": input_type,
                "timeout_seconds": timeout_seconds,
                "expected_input": expected_input,
                "expected_schema": expected_schema,
                "tool_call_id": getattr(msg, "tool_call_id", "") or "",
                "current_agent": current_agent,
                "current_actor": current_actor,
                "scene_id": state.get("scene_id", ""),
                "selected_role_id": state.get("selected_role_id", ""),
            }
            break

    if isinstance(result, dict):
        result["current_agent"] = current_agent
        result["current_actor"] = current_actor
        result["react_step"] = state.get("react_step", 0)
        result["max_steps"] = state.get("max_steps", 12)
        if isinstance(result.get("messages"), list):
            tool_texts: List[str] = []
            for m in result.get("messages", []):
                if isinstance(m, ToolMessage):
                    c = m.content if isinstance(m.content, str) else str(m.content)
                    if isinstance(c, str) and c.startswith("__HITL__"):
                        continue
                    if c:
                        tool_texts.append(c)
            if tool_texts:
                result["last_observation"] = {
                    "type": "tool_result",
                    "actor": current_actor,
                    "content": "\n".join(tool_texts)[:2000],
                }
        return result
    return {
        "messages": result,
        "current_agent": current_agent,
        "current_actor": current_actor,
        "react_step": state.get("react_step", 0),
        "max_steps": state.get("max_steps", 12),
    }
