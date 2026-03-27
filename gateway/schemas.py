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