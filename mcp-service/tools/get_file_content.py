from core.decorators import register_tool
from dataBase.Service import FileService

@register_tool(
    category="file_system",
    description="读取指定文本文件内容。app_id 由运行时注入，无需模型传入。",
)
async def read_file_content(file_id: str, app_id: str = "") -> str:
    """
    读取本地文件内容
    :param file_id: 文件ID
    :param app_id: 运行时注入的应用ID
    :return: 文件内容或错误信息
    """
    file_service = FileService()
    try:
        if not file_id:
            return "file_id 不能为空"
        if not app_id:
            return "app_id 缺失（应由运行时注入）"
        file_doc = file_service.get_file_info(file_id=file_id, app_id=app_id)
        if not file_doc:
            return "文件不存在"

        content = file_doc.get("content")
        return content if content else "文件内容为空"
    except Exception as e:
        return f"读取文件失败: {str(e)}"