# -*- coding: utf-8 -*-

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatResponse(BaseModel):
    session_id: str
    final_message: str
    events: List[Dict[str, Any]]


class UploadResponse(BaseModel):
    session_id: str
    file_name: str
    file_id: Optional[str] = ""
    file_type: List[str] = Field(default_factory=lambda: ["未知"])
    content_preview: Optional[str] = ""
    message: str = "处理完成"
