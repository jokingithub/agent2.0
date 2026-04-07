# -*- coding: utf-8 -*-
"""Agent 创建工厂，基于配置动态创建 Agent"""

from typing import List, Dict, Optional, Tuple
from pathlib import Path
from app.core.llm import get_model, get_model_by_level_id
from app.tools.factory import load_tools_for_sub_agent
from dataBase.ConfigService import SubAgentService, SkillService
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage
from logger import logger

_sub_agent_service = SubAgentService()
_skill_service = SkillService()
_ROOT = Path(__file__).resolve().parents[2]

def _load_skill_refs(skill_ids: List[str]) -> List[Dict[str, str]]:
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
            result.append({"name": name, "description": desc})
        except Exception as e:
            logger.warning(f"读取 skill 失败 skill_id={sid}: {e}")
    return result

def _merge_system_prompt_with_skills(system_prompt: str, skills: List[Dict[str, str]]) -> str:
    if not skills:
        return system_prompt or "你是一个AI助手。"
    base = system_prompt or "你是一个AI助手。"
    lines = [f"{i+1}. {s.get('name','')}：{s.get('description','')}" for i, s in enumerate(skills)]
    skills_text = "\n".join(lines)
    return (
        f"{base}\n\n"
        f"---\n"
        f"你当前可用技能（仅供参考）:\n{skills_text}\n\n"
        f"请遵循：\n"
        f"1. 优先在上述技能范围内完成任务；\n"
        f"2. 不要虚构不存在的技能能力；\n"
        f"3. 超出技能范围时明确说明限制并给出可行方案。"
    )

def _escape_prompt_braces(text: str) -> str:
    if not text:
        return ""
    return text.replace("{", "{{").replace("}", "}}")

def create_agent_from_config(sub_agent_id: str) -> Optional[Tuple]:
    """根据 sub_agent_id 动态创建 agent 实例及工具列表"""
    config = _sub_agent_service.get_by_id(sub_agent_id)
    if not config:
        logger.warning(f"sub_agent '{sub_agent_id}' 不存在")
        return None
    # 模型
    model_id = config.get("model_id")
    llm = get_model_by_level_id(model_id) if model_id else get_model("high")
    # 工具
    tools = load_tools_for_sub_agent(sub_agent_id)
    # 组合系统提示词和技能描述
    system_prompt = config.get("system_prompt") or "你是一个AI助手。"
    skill_ids = config.get("skill_ids", []) or []
    skill_refs = _load_skill_refs(skill_ids)
    merged_prompt = _merge_system_prompt_with_skills(system_prompt, skill_refs)
    merged_prompt = _escape_prompt_braces(merged_prompt)

    prompt = ChatPromptTemplate.from_messages([
        ("system", merged_prompt),
        MessagesPlaceholder(variable_name="messages"),
    ])

    if tools:
        agent = prompt | llm.bind_tools(tools)
    else:
        agent = prompt | llm

    return agent, tools
