# -*- coding: utf-8 -*-
"""通用Agent工厂 - 从配置表动态创建Agent节点"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage
from app.core.llm import get_model, get_model_by_level_id
from app.tools.factory import load_tools_for_sub_agent, load_skill_as_tool
from dataBase.ConfigService import SubAgentService, SkillService
import json
from typing import List, Dict, Any
from pathlib import Path
from logger import logger

_sub_agent_service = SubAgentService()
_skill_service = SkillService()
_ROOT = Path(__file__).resolve().parents[2]

# 本地skills缓存
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

def _load_skill_refs(skill_ids: List[str]) -> List[Dict[str, str]]:
    """
    根据 skill_ids 拉取技能摘要，只保留 name + description
    """
    result: List[Dict[str, str]] = []
    if not skill_ids:
        return result

    for sid in skill_ids:
        try:
            skill = _skill_service.get_by_id(sid)
            if not skill:
                continue
            name = (skill.get("name") or "").strip()
            desc = (skill.get("description") or "").strip()
            if not name:
                continue
            result.append({
                "name": name,
                "description": desc,
            })
        except Exception as e:
            logger.warning(f"读取 skill 失败 skill_id={sid}: {e}")

    return result

def _merge_system_prompt_with_skills(system_prompt: str, skills: List[Dict[str, str]]) -> str:
    if not skills:
        return system_prompt or "你是一个AI助手。"

    base = system_prompt or "你是一个AI助手。"
    lines = []
    for i, s in enumerate(skills, 1):
        lines.append(f"{i}. {s.get('name','')}：{s.get('description','')}")
    skills_text = "\n".join(lines)

    return (
        f"{base}\n\n"
        f"---\n"
        f"你当前可用技能（仅供参考）:\n{skills_text}\n\n"
        f"请遵循：\n"
        f"1. 优先在上述技能范围内完成任务；\n"
        f"2. 不要虚构不存在的技能能力；\n"
        f"3. 若超出技能范围，明确说明限制并给出可行下一步。"
    )


def _escape_prompt_braces(text: str) -> str:
    if not text:
        return ""
    return text.replace("{", "{{").replace("}", "}}")


def create_agent_from_config(sub_agent_id: str):
    """
    从sub_agents表读配置，动态创建Agent。
    返回 (agent_chain, tools) 或 None。
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
    system_prompt = config.get("system_prompt") or "你是一个AI助手。"
    skill_ids = config.get("skill_ids", []) or []
    skill_refs = _load_skill_refs(skill_ids)
    system_prompt = _merge_system_prompt_with_skills(system_prompt, skill_refs)
    system_prompt = _escape_prompt_braces(system_prompt)  # 新增

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
    def node_fn(state):
        result = create_agent_from_config(sub_agent_id)
        if result is None:
            return {
                "messages": [AIMessage(content=f"Agent '{sub_agent_id}' 配置不存在")],
            }

        agent, tools = result

        session_files = state.get("session_files")
        messages = list(state.get("messages", []))

        if session_files and tools:
            file_list = "\n".join([
                f"- {f.get('file_name', 'unknown')} (ID: {f.get('file_id', 'unknown')})"
                for f in session_files
            ])

            from langchain_core.messages import SystemMessage
            messages.insert(0, SystemMessage(content=f"当前会话关联的文件:\n{file_list}"))

        response = agent.invoke({"messages": messages})

        # ===== 关键修改：只返回 messages，不返回其他 state 字段 =====
        return {"messages": [response]}

    return node_fn
