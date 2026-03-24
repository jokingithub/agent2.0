# -*- coding: utf-8 -*-
# 文件：fileUpload/fileUpload.py
# time: 2026/3/18

import hashlib
import os
from typing import Any
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime

from dataBase.Schema import FileModel
from dataBase.Service import FileService, SessionService

from fileUpload.file_classfly import classify_file
from fileUpload.extract_content import extract_content
from fileUpload.element_extraction import element_extraction
from logger import logger

async def save_file(file, session_id) -> dict[str, Any]:
    try:
        file_service = FileService()
        session_service = SessionService()
        file_id = hashlib.md5(await file.read()).hexdigest()
        await file.seek(0)
        # 先检查文件是否已存在，避免重复处理
        if hits := file_service.get_file_info(file_id):
            file_info = FileModel(**hits)
            session_service.add_file_to_session(session_id, file_info=file_info)
            return {
                "session_id": session_id,
                "file_name": hits["file_name"],
                "file_id": hits["file_id"],
                "file_type": hits["file_type"],
                "content_preview": hits["content"][:500] + ("..." if len(hits["content"]) > 500 else ""),
                "message": "文件已存在，返回已有信息"
            }
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        try:
            extracted_content = extract_content(tmp_path)
            file_type = classify_file(extracted_content)

            # TODO: 增加要素抽取的逻辑
            # 对每个分类类型抽取要素，合并结果
            element = {}
            for ft in file_type:
                result = element_extraction(file_content=extracted_content, file_type=ft)
                if result and not result.get("_error") and not result.get("_parse_error"):
                    element.update(result)
            logger.info(f"要素抽取结果: {element}")

            file_data = FileModel(
                file_id=file_id,
                file_name=file.filename,
                file_type=file_type,
                content=extracted_content,
                main_info=element if element else None,
                upload_time=datetime.now()
            )

            session_service.add_file_to_session(session_id=session_id,file_info=file_data)

            preview = extracted_content[:500] + ("..." if len(extracted_content) > 500 else "")

            return {
                "session_id": session_id,
                "file_name": file.filename,
                "file_id": file_id,
                "file_type": file_type,
                "content_preview": preview,
                "message": "文件上传和提取成功"
            }
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            
    except Exception as e:
        return {
            "session_id": session_id,
            "file_name": file.filename,
            "file_id": None,
            "file_type": [],
            "content_preview": None,
            "message": f"文件上传和提取失败: {str(e)}"
        }