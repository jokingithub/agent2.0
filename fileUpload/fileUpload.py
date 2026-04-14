# -*- coding: utf-8 -*-
# 文件：fileUpload/fileUpload.py
# time: 2026/3/26

import hashlib
import os
import re
from pathlib import Path
from typing import Any
from datetime import datetime

from Schema.db_models import FileModel
from dataBase.Service import FileService, SessionService
from dataBase.ConfigService import FileProcessingService

from fileUpload.file_classfly import classify_file
from fileUpload.extract_content import extract_content
from fileUpload.element_extraction import element_extraction
from logger import logger


_fp_service = FileProcessingService()


def _is_blank_content(content: Any) -> bool:
    text = (content or "") if isinstance(content, str) else ""
    text = text.strip()
    if not text:
        return True

    # 这些表示 OCR/提取未产出有效内容
    empty_markers = [
        "[OCR 未识别到文字内容]",
        "读取失败",
    ]
    if text in empty_markers:
        return True
    if text.startswith("提取内容失败"):
        return True

    return False


def _is_empty_main_info(main_info: Any) -> bool:
    if main_info is None:
        return True
    if not isinstance(main_info, dict):
        return False
    if not main_info:
        return True

    # 字典存在但值全空，也视为空（用于后续重试抽取）
    for v in main_info.values():
        if v not in (None, "", [], {}, ()):
            return False
    return True


def _need_reprocess_cached(hit: dict) -> bool:
    return _is_blank_content(hit.get("content")) or _is_empty_main_info(hit.get("main_info"))


def _find_fields_for_type(file_type: str) -> list[str]:
    cfg = _fp_service.get_by_file_type(file_type)
    if cfg and isinstance(cfg.get("fields"), list):
        return [x for x in cfg.get("fields", []) if isinstance(x, str) and x.strip()]

    all_cfg = _fp_service.get_all()
    for item in all_cfg:
        ft = item.get("file_type", "")
        if isinstance(ft, str) and (ft in file_type or file_type in ft):
            fields = item.get("fields") or []
            return [x for x in fields if isinstance(x, str) and x.strip()]
    return []


def _empty_element_payload(file_type: str) -> dict[str, Any]:
    fields = _find_fields_for_type(file_type)
    return {k: None for k in fields}


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
        cached_hit = file_service.get_file_info(file_id, app_id=app_id)
        if cached_hit and not _need_reprocess_cached(cached_hit):
            file_info = FileModel(**cached_hit)
            session_service.add_file_to_session(session_id, file_info=file_info, app_id=app_id)
            return {
                "session_id": session_id,
                "app_id": app_id,
                "file_name": cached_hit["file_name"],
                "file_id": cached_hit["file_id"],
                "file_type": cached_hit["file_type"],
                "content_preview": cached_hit["content"][:500] + ("..." if len(cached_hit["content"]) > 500 else ""),
                "message": "文件已存在，返回已有信息",
            }

        # 命中缓存但内容/要素为空：触发重处理
        if cached_hit and _need_reprocess_cached(cached_hit):
            logger.warning(
                "命中缓存但内容或要素为空，触发重处理: file_id=%s app_id=%s",
                file_id,
                app_id,
            )

        # 新文件：先创建一条“处理中”记录，便于前端轮询处理状态
        if not cached_hit:
            initial_doc = FileModel(
                app_id=app_id,
                file_id=file_id,
                file_name=file.filename,
                file_type=[],
                content="",
                main_info=None,
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
            else:
                # 抽取失败时，将该类型对应字段置空，方便后续重试识别
                empty_payload = _empty_element_payload(ft)
                for k, v in empty_payload.items():
                    element.setdefault(k, v)
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
            "message": "文件上传和提取成功" if not cached_hit else "命中缓存但内容为空，已重新执行OCR与要素抽取",
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
