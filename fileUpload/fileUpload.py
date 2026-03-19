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

from dataBase.Schema import FileModel
from dataBase.Service import FileService

from fileUpload.file_classfly import classify_file
from fileUpload.extract_content import extract_content
from logger import logger

async def save_file(file, session_id):
    try:
        file_service = FileService()
        file_id = hashlib.md5(await file.read()).hexdigest()
        await file.seek(0)

        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        try:
            extracted_content = extract_content(tmp_path)
            file_type = classify_file(extracted_content)

            file_data = FileModel(
                file_id=file_id,
                file_name=file.filename,
                file_type=file_type,
                content=extracted_content
            )
            file_service.save_file_info(file_data)

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