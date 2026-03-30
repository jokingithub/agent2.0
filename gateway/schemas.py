# -*- coding: utf-8 -*-
from typing import Any, Dict, List
from pydantic import BaseModel, Field


class ToolInvokeRequest(BaseModel):
    tool_id: str = Field(..., description="工具ID（支持 tools._id 或 tools.name）")
    params: Dict[str, Any] = Field(default_factory=dict, description="工具调用参数")

class FileInfo(BaseModel):
    app_id: str
    content: str
    file_id: str
    file_name: str
    file_type: List[str]
    upload_time: str
    _id: str
    main_info: Dict[str, Any] = None


class FileProcessingStatus(BaseModel):
    app_id: str
    file_id: str
    file_name: str
    processing_status: str
    processing_stage: str | None = None
    processing_message: str | None = None
    updated_at: str | None = None
    upload_time: str | None = None


class WhitelistReplaceRequest(BaseModel):
    whitelist: List[str] = Field(default_factory=list, description="完整白名单列表（支持 http/https 源或 *）")


class WhitelistItemRequest(BaseModel):
    origin: str = Field(..., min_length=1, description="单个白名单源（例如 http://localhost:3000）")