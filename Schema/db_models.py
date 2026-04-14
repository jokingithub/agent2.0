# -*- coding: utf-8 -*-

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FileModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    app_id: str = ""
    file_id: str
    file_name: str
    file_type: List[str]
    content: str
    file_path: Optional[str] = None
    main_info: Optional[Dict[str, Any]] = None
    processing_status: str = "completed"  # processing / completed / failed
    processing_stage: Optional[str] = None  # received / extracting / classifying / extracting_elements / done / error
    processing_message: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.now)
    upload_time: datetime = Field(default_factory=datetime.now)


class MemoryModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    app_id: str = ""
    session_id: str
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.now)


class FileTypeModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    file_type: List[str]


class SessionModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    app_id: str = ""
    session_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    file_list: List[str] = Field(default_factory=list)
    status: str = "active"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None

    # HITL（Human-in-the-loop）挂起状态
    pending_status: str = "active"  # active / suspended / timeout_failed
    pending_data: Optional[Dict[str, Any]] = None
    pending_expires_at: Optional[str] = None


class ChatLogModel(BaseModel):
    """会话日志"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    app_id: str = ""
    scene_id: str = ""
    session_id: str = ""
    request_content: str = ""
    response_content: str = ""
    cached_tokens: Optional[int] = 0
    cache_hit_calls: Optional[int] = 0
    cache_hit: Optional[bool] = False

    # 耗时
    request_time: Optional[str] = None
    first_token_time: Optional[str] = None
    end_time: Optional[str] = None

    # token消耗
    total_tokens: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None

    # 模型追踪
    model_detail: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="""
        每次LLM调用的详细记录，例如:
        [
            {"seq": 1, "node": "supervisor", "model": "gpt-4o", "prompt_tokens": 120, "completion_tokens": 30},
            {"seq": 2, "node": "quotation", "model": "deepseek-v3", "prompt_tokens": 200, "completion_tokens": 80}
        ]
        """,
    )
    final_model: Optional[str] = Field(default=None, description="最后一次LLM调用的模型名")
