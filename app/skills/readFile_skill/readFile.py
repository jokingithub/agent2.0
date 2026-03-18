from langchain_core.tools import tool
from pathlib import Path
from typing import Annotated
from langgraph.prebuilt import InjectedState
from dataBase.Service import FileService

@tool
def read_file(file_id: str) -> str:
    """读取当前 session 目录内文件内容（支持相对路径，禁止越界）。"""
    file_service = FileService()

    try:
        file_info = file_service.get_file_info(file_id)
        if not file_info:
            return f"未找到文件 ID: {file_id}"

        # 直接返回数据库中存储的内容
        data = {"file_name": file_info["file_name"], "content": file_info["content"]}
        return data
    except Exception as e:
        return f"读取文件错误: {e}"
    