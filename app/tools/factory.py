import importlib
from pathlib import Path

import yaml
from langchain_core.tools import BaseTool, Tool


def _parse_front_matter(md_content: str) -> tuple[dict, str]:
    """解析 Markdown Front Matter，返回(metadata, body)。"""
    if not md_content.startswith("---"):
        raise ValueError("skill.md 缺少 Front Matter，请以 --- 开头。")

    parts = md_content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("skill.md Front Matter 格式错误。")

    _, header_str, body = parts
    metadata = yaml.safe_load(header_str) or {}
    return metadata, body.strip()


def _load_callable(entrypoint: str):
    """按 module_path:function_name 动态导入函数。"""
    if ":" not in entrypoint:
        raise ValueError("entrypoint 格式应为 'module.path:function_name'。")

    module_path, func_name = entrypoint.split(":", 1)
    module = importlib.import_module(module_path)
    func = getattr(module, func_name, None)
    if func is None:
        raise ValueError(f"未在模块 {module_path} 中找到函数 {func_name}。")
    return func


def load_skill_as_tool(skill_dir: str) -> Tool:
    """从 skill 目录加载 Tool。

    目录要求:
    - skill.md (含 front matter)

    front matter 示例:
    ---
    name: calculate
    description: 计算数学表达式
    entrypoint: app.skills.calculate_skill.calculate_skill:calculate
    ---
    """
    skill_md = Path(skill_dir) / "skill.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"未找到 {skill_md}")

    content = skill_md.read_text(encoding="utf-8")
    metadata, body = _parse_front_matter(content)

    name = metadata.get("name")
    description = metadata.get("description", "")
    entrypoint = metadata.get("entrypoint")

    if not name:
        raise ValueError("skill.md 缺少必填字段: name")
    if not entrypoint:
        raise ValueError("skill.md 缺少必填字段: entrypoint")

    loaded = _load_callable(entrypoint)

    # 兼容两种 Skill 形式：
    # 1) 纯函数（callable）
    # 2) 已加 @tool 的 BaseTool（如 StructuredTool）
    if isinstance(loaded, BaseTool):
        if description.strip() or body:
            loaded.description = (
                f"{description.strip()}\n\n详细说明:\n{body}".strip()
                if body
                else description.strip()
            )
        return loaded

    final_description = description.strip() or (loaded.__doc__ or "")
    if body:
        final_description = f"{final_description}\n\n详细说明:\n{body}".strip()

    return Tool(name=name, description=final_description, func=loaded)