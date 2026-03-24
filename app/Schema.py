# -*- coding: utf-8 -*-
# 文件：app/Schema.py
# time: 2026/3/10

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., description="用户输入")
    app_id: str = Field(default="default", description="应用 ID")
    scene_id: str = Field(default="default", description="场景 ID")
    recursion_limit: int = Field(50, ge=1, le=200)


class ChatResponse(BaseModel):
    session_id: str
    final_message: str
    events: list[dict[str, Any]]


class UploadResponse(BaseModel):
    session_id: str
    file_name: str
    file_id: Optional[str] = ""
    file_type: Optional[list[str]] = "未知"
    content_preview: Optional[str] = ""
    message: str = "处理完成"
