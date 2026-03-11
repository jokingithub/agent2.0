from langchain_core.tools import tool
from pathlib import Path
from typing import Annotated
from langgraph.prebuilt import InjectedState


# 工作区根目录
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SESSIONS_ROOT = WORKSPACE_ROOT / "sessions"


def _resolve_in_session(file_path: str, session_id: str) -> Path:
    """将输入路径解析为会话目录内绝对路径；越界则抛错。"""
    if not session_id:
        raise ValueError("缺少 session_id")

    session_root = (SESSIONS_ROOT / session_id).resolve()
    session_root.mkdir(parents=True, exist_ok=True)

    raw = Path(file_path.strip())

    # 绝对路径直接使用；相对路径按会话目录解析
    candidate = raw if raw.is_absolute() else (session_root / raw)
    resolved = candidate.resolve()

    # Python 3.10 兼容的会话目录越界检查
    if session_root == resolved or session_root in resolved.parents:
        return resolved
    raise ValueError("禁止访问当前 session 目录之外的文件")

@tool
def read_file(
    file_path: str,
    session_id: Annotated[str, InjectedState("session_id")],
) -> str:
    """读取当前 session 目录内文件内容（支持相对路径，禁止越界）。"""
    try:
        target = _resolve_in_session(file_path, session_id)
        if not target.exists():
            return f"读取文件错误: 文件不存在: {target}"
        if not target.is_file():
            return f"读取文件错误: 不是文件: {target}"

        with open(target, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"读取文件错误: {e}"
    