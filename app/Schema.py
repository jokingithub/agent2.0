# -*- coding: utf-8 -*-
# 文件：app/Schema.py
# time: 2026/3/10

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any

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

# ============================================================
# Session & Memory 管理接口请求模型
# ============================================================

class CreateSessionRequest(BaseModel):
    """创建会话"""
    session_id: str = Field(..., description="会话ID")
    app_id: str = Field("", description="应用ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="会话元数据")
    status: str = Field("active", description="会话状态")


class UpdateSessionRequest(BaseModel):
    """更新会话"""
    app_id: str = Field("", description="应用ID（用于定位）")
    status: Optional[str] = Field(None, description="会话状态")
    metadata: Optional[Dict[str, Any]] = Field(None, description="会话元数据")


class AppendMessageRequest(BaseModel):
    """追加消息到记忆"""
    app_id: str = Field("", description="应用ID")
    role: str = Field(..., description="角色: user / assistant / system")
    content: str = Field(..., description="消息内容")
    model_name: str = Field("", description="模型名（assistant 消息时记录）")
    agent_name: str = Field("", description="Agent名（assistant 消息时记录）")


class ReplaceMessagesRequest(BaseModel):
    """替换整个消息列表"""
    app_id: str = Field("", description="应用ID")
    messages: List[Dict[str, Any]] = Field(..., description="完整消息列表")
