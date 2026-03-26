# -*- coding: utf-8 -*-
# 文件：fileUpload/fileUpload.py
# time: 2026/3/26

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from datetime import datetime

from dataBase.Schema import FileModel
from dataBase.Service import FileService, SessionService

from fileUpload.file_classfly import classify_file
from fileUpload.extract_content import extract_content
from fileUpload.element_extraction import element_extraction
from logger import logger


def _safe_filename(name: str) -> str:
    """清理文件名，防止路径注入和非法字符"""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-.()\u4e00-\u9fa5]", "_", name)
    return cleaned or "unnamed"


def _write_upload_file(
    content_bytes: bytes,
    origin_name: str,
    app_id: str,
    session_id: str,
    file_id: str,
) -> tuple[str, bool]:
    """
    写入上传文件并返回路径
    返回: (file_path, is_temp_file)

    规则：
    1) 未配置 FILE_STORAGE_ROOT：保持现有行为 -> 写 /tmp 临时文件
    2) 配置了 FILE_STORAGE_ROOT：写持久目录 -> {root}/{app_id}/{session_id}/{safe_name}_{file_id}{ext}
    """
    storage_root = os.getenv("FILE_STORAGE_ROOT", "").strip()

    # 未配置：保持当前 /tmp 行为
    if not storage_root:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=Path(origin_name).suffix or "",
            dir=tempfile.gettempdir(),
        ) as tmp_file:
            tmp_file.write(content_bytes)
            return tmp_file.name, True

    # 已配置：持久目录
    root_path = Path(storage_root).resolve()
    ext = Path(origin_name).suffix or ""
    safe_stem = _safe_filename(Path(origin_name).stem)
    file_name = f"{safe_stem}_{file_id}{ext}"
    target_path = root_path / (app_id or "default") / session_id / file_name
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "wb") as f:
        f.write(content_bytes)

    return str(target_path), False


async def save_file(file, session_id, app_id: str = "") -> dict[str, Any]:
    try:
        file_service = FileService()
        session_service = SessionService()

        # 读取文件并计算 file_id
        content_bytes = await file.read()
        file_id = hashlib.md5(content_bytes).hexdigest()
        await file.seek(0)

        # 去重（同 file_id + app_id）
        if hits := file_service.get_file_info(file_id, app_id=app_id):
            file_info = FileModel(**hits)
            session_service.add_file_to_session(session_id, file_info=file_info, app_id=app_id)
            return {
                "session_id": session_id,
                "app_id": app_id,
                "file_name": hits["file_name"],
                "file_id": hits["file_id"],
                "file_type": hits["file_type"],
                "content_preview": hits["content"][:500] + ("..." if len(hits["content"]) > 500 else ""),
                "message": "文件已存在，返回已有信息",
            }

        # 写文件（tmp 或持久目录）
        file_path, is_temp_file = _write_upload_file(
            content_bytes=content_bytes,
            origin_name=file.filename,
            app_id=app_id,
            session_id=session_id,
            file_id=file_id,
        )

        try:
            # 用写入后的路径做解析（日志会打印这个路径）
            extracted_content = extract_content(file_path)
            file_type = classify_file(extracted_content)

            # 要素抽取（多分类合并）
            element = {}
            for ft in file_type:
                result = element_extraction(file_content=extracted_content, file_type=ft)
                if result and not result.get("_error") and not result.get("_parse_error"):
                    element.update(result)
            logger.info(f"要素抽取结果: {element}")

            file_data = FileModel(
                app_id=app_id,
                file_id=file_id,
                file_name=file.filename,
                file_type=file_type,
                content=extracted_content,
                file_path=file_path,  # 新增：存储上传文件路径
                main_info=element if element else None,
                upload_time=datetime.now(),
            )

            session_service.add_file_to_session(
                session_id=session_id,
                file_info=file_data,
                app_id=app_id,
            )

            preview = extracted_content[:500] + ("..." if len(extracted_content) > 500 else "")

            return {
                "session_id": session_id,
                "app_id": app_id,
                "file_name": file.filename,
                "file_id": file_id,
                "file_type": file_type,
                "content_preview": preview,
                "message": "文件上传和提取成功",
            }

        finally:
            # 保持当前行为：如果是 /tmp 临时文件，处理完后删除
            if is_temp_file and os.path.exists(file_path):
                os.remove(file_path)

    except Exception as e:
        logger.error(f"文件上传和提取失败: {e}", exc_info=True)
        return {
            "session_id": session_id,
            "file_name": file.filename if file else "",
            "file_id": None,
            "file_type": [],
            "content_preview": None,
            "message": f"文件上传和提取失败: {str(e)}",
        }
