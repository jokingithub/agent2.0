# -*- coding: utf-8 -*-
from core.decorators import register_tool
from dataBase.Service import FileService

@register_tool(category="file", arg_name="file_id")
def read_file_content(file_id: str, app_id: str = "") -> str:
    """
    读取指定文件的完整内容（支持 app_id 隔离）。

    Args:
        file_id: 文件ID
        app_id: 应用ID（强烈建议传，避免跨app误读）

    Returns:
        文件内容字符串；失败返回错误信息
    """
    try:
        file_service = FileService()
        doc = file_service.get_file_info(file_id=file_id, app_id=app_id or None)
        if not doc:
            if app_id:
                return f"未找到文件: file_id={file_id}, app_id={app_id}"
            return f"未找到文件: file_id={file_id}"

        content = doc.get("content", "") or ""
        if not content.strip():
            return f"文件 {doc.get('file_name', file_id)} 内容为空"

        return content
    except Exception as e:
        return f"读取文件错误: {e}"
