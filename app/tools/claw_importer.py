# -*- coding: utf-8 -*-
"""
ClawHub Skill 包一键导入器

流程：
  1. 前端上传 .zip / .tar.gz 压缩包
  2. 后端解压到 /app/skills/<dir_name>/
  3. 解析 SKILL.md frontmatter + body
  4. 自动查找 run_command 工具
  5. 创建 skill（绑定 run_command）
  6. 返回 skill_id + 建议的 system_prompt

env_vars / API key 统一通过 .env 注入到 mcp-service 容器，不存入数据库。
"""

import os
import json
import shutil
import zipfile
import tarfile
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import yaml

from logger import logger
from dataBase.ConfigService import ToolService, SkillService
from Schema import SkillModel

_tool_service = ToolService()
_skill_service = SkillService()

# mcp-service 容器内 skills 挂载路径
MCP_SKILLS_BASE = "/app/skills"
# main-app 容器内 skills 路径（和 mcp-service 共享同一宿主机目录）
LOCAL_SKILLS_BASE = "/app/skills"


# ============================================================
# 压缩包处理
# ============================================================

def extract_skill_archive(
    file_path: str,
    filename: str,
    target_base: str = LOCAL_SKILLS_BASE,
) -> str:
    """
    解压 skill 压缩包到 target_base 目录。

    支持 .zip / .tar.gz / .tgz
    自动处理单根目录情况（如 zip 内只有一个顶层目录）。

    Args:
        file_path: 临时文件路径
        filename: 原始文件名（用于判断格式）
        target_base: 解压目标基础目录

    Returns:
        解压后的 skill 目录绝对路径
    """
    os.makedirs(target_base, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 解压到临时目录
        lower = filename.lower()
        if lower.endswith(".zip"):
            with zipfile.ZipFile(file_path, "r") as zf:
                zf.extractall(tmp_dir)
        elif lower.endswith((".tar.gz", ".tgz")):
            with tarfile.open(file_path, "r:gz") as tf:
                tf.extractall(tmp_dir)
        elif lower.endswith(".tar"):
            with tarfile.open(file_path, "r:") as tf:
                tf.extractall(tmp_dir)
        else:
            raise ValueError(f"不支持的压缩格式: {filename}（支持 .zip / .tar.gz / .tgz）")

        # 找到实际的 skill 根目录
        # 如果解压后只有一个顶层目录，进入它
        entries = [e for e in os.listdir(tmp_dir) if not e.startswith(".")]
        if len(entries) == 1:
            single = os.path.join(tmp_dir, entries[0])
            if os.path.isdir(single):
                skill_src = single
            else:
                skill_src = tmp_dir
        else:
            skill_src = tmp_dir

        # 验证是否包含 .md 文件
        if not _find_skill_md(Path(skill_src)):
            raise ValueError("压缩包中未找到 SKILL.md 或任何 .md 文件，不是有效的 ClawHub skill 包")

        # 确定目标目录名
        dir_name = Path(skill_src).name
        # 如果是临时目录名，用压缩包文件名
        if dir_name.startswith("tmp") or dir_name == ".":
            dir_name = Path(filename).stem
            # 去掉 .tar 后缀
            if dir_name.endswith(".tar"):
                dir_name = dir_name[:-4]

        target_dir = os.path.join(target_base, dir_name)

        # 如果目标已存在，先删除
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)

        # 移动到目标位置
        shutil.copytree(skill_src, target_dir)

    logger.info(f"Skill 包已解压到: {target_dir}")
    return target_dir


# ============================================================
# 自动查找 run_command 工具
# ============================================================

def _find_run_command_tool_id() -> str:
    """从 tools 表中自动查找 run_command 工具的 ID"""
    all_tools = _tool_service.get_all() or []
    for tool in all_tools:
        if tool.get("name") == "run_command" and tool.get("enabled"):
            return tool["_id"]

    raise ValueError(
        "未找到已启用的 run_command 工具。"
        "请先在 tools 表中创建 name='run_command' 的 MCP 工具。"
    )


# ============================================================
# 主入口
# ============================================================

def import_claw_skill(
    skill_dir: str,
    run_command_tool_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    导入单个 ClawHub skill 目录：
    1) 解析 SKILL.md frontmatter
    2) 自动绑定 run_command 工具
    3) 创建 skill
    4) 返回建议 system_prompt（不入库）
    """
    skill_path = Path(skill_dir)
    if not skill_path.exists() or not skill_path.is_dir():
        raise FileNotFoundError(f"Skill 目录不存在: {skill_dir}")

    # 1) run_command 工具
    if not run_command_tool_id:
        run_command_tool_id = _find_run_command_tool_id()
    else:
        rc_tool = _tool_service.get_by_id(run_command_tool_id)
        if not rc_tool:
            raise ValueError(f"run_command 工具不存在: {run_command_tool_id}")

    # 2) 读取 skill markdown
    skill_md_path = _find_skill_md(skill_path)
    if not skill_md_path:
        raise FileNotFoundError(f"未找到 SKILL.md 或 .md 文件: {skill_dir}")

    md_content = skill_md_path.read_text(encoding="utf-8")
    frontmatter, md_body = _parse_frontmatter(md_content)

    skill_name = frontmatter.get("name", skill_path.name)
    description = frontmatter.get("description", f"ClawHub skill: {skill_name}")
    metadata = frontmatter.get("metadata", {}) or {}

    claw_meta = metadata.get("openclaw") or metadata.get("clawdbot") or {}
    required_env = claw_meta.get("requires", {}).get("env", []) or []
    required_bins = claw_meta.get("requires", {}).get("bins", []) or []
    emoji = claw_meta.get("emoji", "🔧")

    scripts_dir = skill_path / "scripts"
    has_scripts = scripts_dir.exists() and any(scripts_dir.iterdir())
    skill_type = "script" if has_scripts else "instruction"

    display_name = f"{emoji} {skill_name}"

    # 3) 同名检查
    existing_skills = _skill_service.get_all() or []
    for s in existing_skills:
        if (s.get("name") or "").strip() == display_name:
            raise ValueError(f"已存在同名技能「{display_name}」(ID: {s.get('_id')})")

    # 4) 先构造 prompt hint（仅返回，不写入 skill 表）
    system_prompt_hint = _build_system_prompt(
        skill_name=skill_name,
        md_body=md_body,
        skill_dir_name=skill_path.name,
        has_scripts=has_scripts,
        required_env=required_env,
    )

    # 5) 创建 skill（注意：你当前 SkillModel 没有 system_prompt 字段，不要传）
    skill_model = SkillModel(
        name=display_name,
        description=description,
        tool_ids=[run_command_tool_id],
        system_prompt=system_prompt_hint,
    )
    skill_id = _skill_service.create(skill_model)

    # 6) 返回
    return {
        "skill_id": skill_id,
        "skill_name": display_name,
        "description": description,
        "skill_type": skill_type,
        "required_env": required_env,
        "required_bins": required_bins,
        "system_prompt_hint": system_prompt_hint,
    }


# ============================================================
# 扫描
# ============================================================

def scan_and_list_skills(skills_base_dir: str = LOCAL_SKILLS_BASE) -> List[Dict[str, Any]]:
    """
    扫描 skills 目录，列出所有可导入的 skill 包（不执行导入）。
    """
    base = Path(skills_base_dir)
    if not base.exists():
        return []

    results = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue

        md_path = _find_skill_md(child)
        if not md_path:
            continue

        try:
            md_content = md_path.read_text(encoding="utf-8")
            frontmatter, _ = _parse_frontmatter(md_content)
        except Exception:
            continue

        name = frontmatter.get("name", child.name)
        description = frontmatter.get("description", "")
        metadata = frontmatter.get("metadata", {})
        claw_meta = metadata.get("openclaw") or metadata.get("clawdbot") or {}

        scripts_dir = child / "scripts"
        has_scripts = scripts_dir.exists() and any(scripts_dir.iterdir())

        results.append({
            "dir_name": child.name,
            "path": str(child),
            "name": name,
            "description": description,
            "type": "script" if has_scripts else "instruction",
            "required_env": claw_meta.get("requires", {}).get("env", []),
            "required_bins": claw_meta.get("requires", {}).get("bins", []),
            "emoji": claw_meta.get("emoji", "🔧"),
        })

    return results


# ============================================================
# 内部函数
# ============================================================

def _find_skill_md(skill_path: Path) -> Optional[Path]:
    """查找 skill 的主 md 文件"""
    # 优先 SKILL.md
    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        return skill_md

    # 其次根目录下任意 .md（排除 README.md 和 references/）
    md_files = [
        f for f in skill_path.glob("*.md")
        if f.name.upper() != "README.MD"
    ]
    if md_files:
        return md_files[0]

    return None


def _parse_frontmatter(md_content: str) -> Tuple[dict, str]:
    """解析 Markdown frontmatter（YAML 头部）"""
    if not md_content.startswith("---"):
        return {}, md_content

    parts = md_content.split("---", 2)
    if len(parts) < 3:
        return {}, md_content

    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        frontmatter = {}

    body = parts[2].strip()
    return frontmatter, body


def _build_system_prompt(
    skill_name: str,
    md_body: str,
    skill_dir_name: str,
    has_scripts: bool,
    required_env: List[str],
) -> str:
    """构建 skill 的 system_prompt（仅包含技能文档和必要上下文）"""

    mcp_skill_path = f"{MCP_SKILLS_BASE}/{skill_dir_name}"

    parts = []

    if has_scripts:
        parts.append(f"以下技能的脚本位于: `{mcp_skill_path}/`")
        parts.append("")

    if required_env:
        env_list = "、".join(f"`{e}`" for e in required_env)
        parts.append(f"以下环境变量已配置: {env_list}")
        parts.append("")

    parts.extend([
        f"## {skill_name} 技能文档",
        "",
        md_body,
    ])

    return "\n".join(parts)

def auto_import_all_skills(skills_base_dir: str = LOCAL_SKILLS_BASE) -> List[Dict[str, Any]]:
    """
    启动时自动扫描 skills 目录，跳过已导入的，导入新的。
    单个 skill 失败不影响其他。
    """
    results = []

    base = Path(skills_base_dir)
    if not base.exists():
        logger.info(f"Skills 目录不存在，跳过自动导入: {skills_base_dir}")
        return results

    try:
        run_command_tool_id = _find_run_command_tool_id()
    except ValueError as e:
        logger.warning(f"自动导入跳过：{e}")
        return results

    existing_names = set()
    for s in (_skill_service.get_all() or []):
        name = (s.get("name") or "").strip()
        if name:
            existing_names.add(name)

    available = scan_and_list_skills(skills_base_dir)
    if not available:
        logger.info("Skills 目录为空，无需导入")
        return results

    for skill_info in available:
        display_name = f"{skill_info['emoji']} {skill_info['name']}"

        if display_name in existing_names:
            logger.info(f"⏭️  跳过已存在: {display_name}")
            continue

        try:
            result = import_claw_skill(
                skill_dir=skill_info["path"],
                run_command_tool_id=run_command_tool_id,
            )
            results.append(result)
            logger.info(f"✅ 自动导入成功: {display_name}")
        except Exception as e:
            logger.warning(f"⚠️  自动导入失败 [{display_name}]: {e}")

    if results:
        logger.info(f"📦 自动导入完成，共导入 {len(results)} 个 skill")
    else:
        logger.info("📦 自动导入完成，无新 skill 需要导入")

    return results
