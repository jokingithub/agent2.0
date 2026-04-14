import subprocess
import os
import json
from core.decorators import register_tool

# 安全黑名单
_BLOCKED_PATTERNS = [
    "rm -rf /", "mkfs", "dd if=", ":(){",
    "chmod -R 777 /", "shutdown", "reboot",
    "> /dev/sd", "mv / ",
]


@register_tool(category="system")
def run_command(command: str, working_dir: str = "", timeout: int = 60) -> str:
    """执行 shell 命令并返回输出结果。用于调用 curl、python3 等命令行工具。

    Args:
        command: 要执行的 shell 命令
        working_dir: 工作目录（可选，默认为当前目录）
        timeout: 超时秒数（默认60）
    """
    # 安全检查
    cmd_lower = command.lower().strip()
    for pattern in _BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return f"安全拒绝：命令包含危险操作 '{pattern}'"

    try:
        cwd = working_dir if working_dir and os.path.isdir(working_dir) else None

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=os.environ.copy(),
        )

        output_parts = []
        if result.stdout.strip():
            output_parts.append(result.stdout.strip())
        if result.stderr.strip():
            output_parts.append(f"[STDERR] {result.stderr.strip()}")

        if not output_parts:
            return f"命令执行完成，退出码: {result.returncode}，无输出"

        output = "\n".join(output_parts)

        # 截断过长输出
        MAX_LEN = 8000
        if len(output) > MAX_LEN:
            output = output[:MAX_LEN] + f"\n... [输出被截断，共 {len(output)} 字符]"

        return output

    except subprocess.TimeoutExpired:
        return f"命令执行超时（{timeout}秒）"
    except Exception as e:
        return f"命令执行失败: {e}"
