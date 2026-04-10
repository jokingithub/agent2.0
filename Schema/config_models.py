# -*- coding: utf-8 -*-

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ModelConnectionModel(BaseModel):
    """模型连接"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    protocol: str  # openai / deepseek / aliyun
    base_url: str
    api_key: str
    models: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ModelLevelModel(BaseModel):
    """模型分级"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    name: str
    level: int  # 优先级，1最高
    connection_id: str
    model: str
    max_retry: int = 3
    timeout: int = 30
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ToolModel(BaseModel):
    """工具（MCP / HTTP / workflow 统一管理）"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    name: str
    type: str  # mcp / http
    category: str  # web_search / chart / workflow / ocr / enterprise / api
    description: Optional[str] = None
    enabled: bool = True

    # 调用目标
    url: Optional[str] = None
    method: str = "POST"

    # 调用配置
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="""
        {
            "path": "/api/v1/query",
            "extra_headers": {},
            "auth_required": false,
            "timeout_sec": 30
        }
        MCP额外字段:
        {
            "tool_name": "web_search",
            "transport": "sse"
        }
        """,
    )

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class RoleModel(BaseModel):
    """角色/人设"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    name: str
    business_knowledge: Optional[str] = None
    system_prompt: str
    main_model_id: str
    fallback_model_id: Optional[str] = None
    sub_agent_ids: List[str] = Field(default_factory=list)
    tool_ids: List[str] = Field(default_factory=list)  # ← 新增：role 直接关联的工具
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SubAgentModel(BaseModel):
    """子Agent"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    name: str
    description: Optional[str] = None
    system_prompt: str
    model_id: str
    skill_ids: List[str] = Field(default_factory=list)
    tool_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SkillModel(BaseModel):
    """技能"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    name: str
    description: str
    tool_ids: List[str] = Field(default_factory=list)
    system_prompt: Optional[str] = Field(default=None, description="技能提示词，加载时自动注入到 sub_agent 上下文")  # ← 新增
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class FileProcessingModel(BaseModel):
    """文件处理 - 要素抽取配置"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    file_type: str
    fields: List[str] = Field(default_factory=list)
    prompt: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SceneModel(BaseModel):
    """场景配置"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    scene_code: str
    available_role_ids: List[str] = Field(default_factory=list)
    route_key: Optional[str] = None
    report_config: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PromptModel(BaseModel):
    """Prompt 模板配置"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    name: str
    prompt_type: str = "general"  # system / role / sub_agent / workflow / general
    content: str
    description: Optional[str] = None
    variables: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    enabled: bool = True
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
