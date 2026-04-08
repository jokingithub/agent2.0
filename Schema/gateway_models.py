# -*- coding: utf-8 -*-

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GatewayEnvModel(BaseModel):
    """网关环境配置"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    port: int = 8000
    whitelist: List[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.now)


class GatewayAppModel(BaseModel):
    """网关 - 外部调用配置"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    app_name: str
    app_id: str
    auth_token: str
    available_scenes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="""
        [
            {
                "scene_code": "quotation",
                "features": ["chat", "upload", "report"]
            },
            {
                "scene_code": "review",
                "features": ["chat"]
            }
        ]
        """,
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class GatewayChannelModel(BaseModel):
    """网关 - 渠道配置"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    channel: str  # wechat_work / feishu / dingtalk
    enabled: bool = False
    webhook_url: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
