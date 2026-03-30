from langchain_core.tools import tool
from dataBase.Service import FileService

@tool
def read_file_content(file_id: str) -> str:
    """读取指定文件的完整内容。

    Args:
        file_id: 文件ID

    Returns:
        文件内容字符串，如果文件不存在则返回错误信息
    """
    file_service = FileService()

    try:
        file_info = file_service.get_file_info(file_id)
        if not file_info:
            return f"未找到文件 ID: {file_id}"

        content = file_info.get("content", "")
        if not content:
            return f"文件 {file_info.get('file_name', file_id)} 内容为空"

        return content

    except Exception as e:
        return f"读取文件错误: {e}"
