# -*- coding: utf-8 -*-
# 文件：fileUpload/fileUpload.py
# time: 2026/3/26

import hashlib
import os
import re
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
    file_id: str,
) -> str:
    """
    写入上传文件到持久目录并返回路径。

    规则：
    - 默认写入项目目录下 uploads/
    - 可通过 FILE_STORAGE_ROOT 覆盖根目录
    - 按 app_id 分层：{root}/{app_id}/{safe_name}_{file_id}{ext}
    """
    storage_root = os.getenv("FILE_STORAGE_ROOT", "").strip()
    if storage_root:
        root_path = Path(storage_root).resolve()
    else:
        project_root = Path(__file__).resolve().parents[1]
        root_path = (project_root / "uploads").resolve()

    ext = Path(origin_name).suffix or ""
    safe_stem = _safe_filename(Path(origin_name).stem)
    file_name = f"{safe_stem}_{file_id}{ext}"
    target_path = root_path / (app_id or "default") / file_name
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "wb") as f:
        f.write(content_bytes)

    return str(target_path)


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

        # 新文件：先创建一条“处理中”记录，便于前端轮询处理状态
        initial_doc = FileModel(
            app_id=app_id,
            file_id=file_id,
            file_name=file.filename,
            file_type=[],
            content="",
            processing_status="processing",
            processing_stage="received",
            processing_message="文件已接收，等待处理",
            upload_time=datetime.now(),
        )
        file_service.save_file_info(initial_doc)


        # 写文件（tmp 或持久目录）
        file_path = _write_upload_file(
            content_bytes=content_bytes,
            origin_name=file.filename,
            app_id=app_id,
            file_id=file_id,
        )

        # 用写入后的路径做解析（日志会打印这个路径）
        file_service.update_processing_status(
            file_id=file_id,
            app_id=app_id,
            processing_status="processing",
            processing_stage="extracting",
            processing_message="正在提取文件内容",
            extra_fields={"file_path": file_path},
        )
        extracted_content = extract_content(file_path)

        file_service.update_processing_status(
            file_id=file_id,
            app_id=app_id,
            processing_status="processing",
            processing_stage="classifying",
            processing_message="正在识别文件类型",
            extra_fields={"content": extracted_content},
        )
        file_type = classify_file(extracted_content)

        # 要素抽取（多分类合并）
        file_service.update_processing_status(
            file_id=file_id,
            app_id=app_id,
            processing_status="processing",
            processing_stage="extracting_elements",
            processing_message="正在抽取关键信息",
            extra_fields={"file_type": file_type},
        )
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

        file_service.update_processing_status(
            file_id=file_id,
            app_id=app_id,
            processing_status="completed",
            processing_stage="done",
            processing_message="文件处理完成",
            extra_fields={
                "file_name": file.filename,
                "file_type": file_type,
                "content": extracted_content,
                "main_info": element if element else None,
                "file_path": file_path,
            },
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

    except Exception as e:
        logger.error(f"文件上传和提取失败: {e}", exc_info=True)
        try:
            if 'file_id' in locals():
                file_service = FileService()
                file_service.update_processing_status(
                    file_id=file_id,
                    app_id=app_id,
                    processing_status="failed",
                    processing_stage="error",
                    processing_message=str(e),
                )
        except Exception:
            pass
        return {
            "session_id": session_id,
            "app_id": app_id,
            "file_name": file.filename if file else "",
            "file_id": None,
            "file_type": [],
            "content_preview": None,
            "message": f"文件上传和提取失败: {str(e)}",
        }
