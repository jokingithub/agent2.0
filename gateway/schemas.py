# -*- coding: utf-8 -*-
from typing import Any, Dict
from pydantic import BaseModel, Field


class ToolInvokeRequest(BaseModel):
    tool_id: str = Field(..., description="工具ID（支持 tools._id 或 tools.name）")
    params: Dict[str, Any] = Field(default_factory=dict, description="工具调用参数")
