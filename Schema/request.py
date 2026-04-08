# -*- coding: utf-8 -*-

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# 源定义在 gateway/schemas.py，此处 re-export 保持统一入口
from gateway.schemas import WhitelistReplaceRequest, WhitelistItemRequest  # noqa: F401


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., description="用户输入")
    app_id: str = Field(..., min_length=1, description="应用 ID（必填）")
    scene_id: str = Field(default="default", description="场景 ID")
    role_id: str = Field(default="", description="指定角色 ID（可选，不传则用场景默认第一个）")
    recursion_limit: int = Field(50, ge=1, le=200)


class GatewayAppCreateRequest(BaseModel):
    app_name: str = Field(..., description="应用名称")
    available_scenes: List[Dict[str, Any]] = Field(default_factory=list, description="可用场景及功能")
    description: Optional[str] = Field(default=None, description="描述")


class ModelConnectionCreateRequest(BaseModel):
    protocol: str = Field(..., description="渠道协议，如 openai / deepseek / aliyun")
    base_url: str = Field(..., description="模型服务基础地址")
    api_key: str = Field(..., description="模型服务密钥")
    description: Optional[str] = Field(default=None, description="连接描述")
    models: Optional[List[str]] = Field(
        default=None,
        description="可选：手工指定模型列表；不传则由后端自动探测/保持空列表",
    )


class ModelConnectionUpdateRequest(BaseModel):
    protocol: Optional[str] = Field(default=None, description="渠道协议")
    base_url: Optional[str] = Field(default=None, description="模型服务基础地址")
    api_key: Optional[str] = Field(default=None, description="模型服务密钥")
    description: Optional[str] = Field(default=None, description="连接描述")
    models: Optional[List[str]] = Field(default=None, description="可选：手工覆盖模型列表；不传则按连接信息自动刷新")


class MCPToolSyncRequest(BaseModel):
    url: Optional[str] = Field(default=None, description="MCP SSE地址，如 http://127.0.0.1:9001/sse")
    default_category: str = Field(default="mcp", description="当远端工具未提供分类时使用的默认分类")
    dry_run: bool = Field(default=False, description="仅预览，不写入数据库")
    prune_missing: bool = Field(default=False, description="是否自动下线远端已不存在的本地MCP工具")


class ElementExtractionModelConfigRequest(BaseModel):
    model_id: str = Field(..., min_length=1, description="模型分级ID（与 sub_agents.model_id 一致）")


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


class ResumeHITLRequest(BaseModel):
    """恢复 HITL 挂起交互"""
    app_id: str = Field(..., min_length=1, description="应用ID")
    interaction_id: str = Field(..., min_length=1, description="交互ID")
    user_input: Any = Field(..., description="用户输入（文本/审批值/结构化对象）")
    recursion_limit: int = Field(30, ge=1, le=200, description="恢复后续跑图的递归上限")
