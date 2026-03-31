# -*- coding: utf-8 -*-
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any, Dict
from datetime import datetime
from logger import logger

class FileModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    app_id: str = ""
    file_id: str
    file_name: str
    file_type: List[str]
    content: str
    file_path: Optional[str] = None   # 新增：持久化文件路径
    main_info: Optional[Dict[str, Any]] = None
    processing_status: str = "completed"   # processing / completed / failed
    processing_stage: Optional[str] = None  # received / extracting / classifying / extracting_elements / done / error
    processing_message: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.now)
    upload_time: datetime = Field(default_factory=datetime.now)

class MemoryModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    app_id: str = ""
    session_id: str
    messages: List[Dict[str, Any]] = Field(default_factory=list)  # 改 str → Any，支持 model 字段
    updated_at: datetime = Field(default_factory=datetime.now)

class FileTypeModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    file_type: List[str]

class SessionModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    app_id: str = ""                # 新增：应用隔离
    session_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    file_list: List[str] = Field(default_factory=list)

#============================================================
# 配置相关模型
# ============================================================

# ---------- 系统配置 ----------

class ModelConnectionModel(BaseModel):
    """模型连接"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    protocol: str# openai / deepseek / aliyun
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
    name: str                # 主力 / 备用 / 兜底
    level: int                             # 优先级，1最高
    connection_id: str# 关联 ModelConnection
    model: str                             # 具体模型名
    max_retry: int = 3
    timeout: int = 30                      # 秒
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


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
    available_scenes: List[Dict[str, Any]] = Field(default_factory=list, description="""
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
    """)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)



class GatewayChannelModel(BaseModel):
    """网关 - 渠道配置"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    channel: str                # wechat_work / feishu / dingtalk
    enabled: bool = False
    webhook_url: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ToolModel(BaseModel):
    """工具（MCP / HTTP / workflow 统一管理）"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    name: str
    type: str                              # mcp / http
    category: str                          # web_search / chart / workflow / ocr / enterprise / api
    description: Optional[str] = None
    enabled: bool = True

    # 调用目标
    url: Optional[str] = None              # 完整URL 或 基础URL（如 https://api.company.com）
    method: str = "POST"                   # HTTP方法，从顶层提出来，不藏在config里

    # 调用配置 — 和 gateway/store.py build_tool_target() 对齐
    config: Optional[Dict[str, Any]] = Field(default=None, description="""
        {
            "path": "/api/v1/query",       # 路径，拼在url后面（url是相对路径时拼backend_base_url）
            "extra_headers": {},           # 额外请求头（如第三方API key）
            "auth_required": false,        # 是否需要网关鉴权
            "timeout_sec": 30              # 超时秒数
        }
        MCP额外字段:
        {
            "tool_name": "web_search",     # MCP工具名
            "transport": "sse"             # MCP传输方式
        }
    """)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)



class ChatLogModel(BaseModel):
    """会话日志"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    app_id: str = ""
    scene_id: str = ""
    session_id: str = ""
    request_content: str = ""
    response_content: str = ""
    # 耗时
    request_time: Optional[str] = None
    first_token_time: Optional[str] = None
    end_time: Optional[str] = None
    # token消耗
    total_tokens: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    # ===== 新增：模型追踪 =====
    model_detail: Optional[List[Dict[str, Any]]] = Field(default=None, description="""
        每次LLM调用的详细记录，例如:
        [
            {"seq": 1, "node": "supervisor", "model": "gpt-4o", "prompt_tokens": 120, "completion_tokens": 30},
            {"seq": 2, "node": "quotation", "model": "deepseek-v3", "prompt_tokens": 200, "completion_tokens": 80}
        ]
    """)
    final_model: Optional[str] = Field(default=None, description="最后一次LLM调用的模型名")





# ---------- 业务配置 ----------

class RoleModel(BaseModel):
    """角色/人设"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    name: str
    business_knowledge: Optional[str] = None
    system_prompt: str
    main_model_id: str                # 关联 ModelLevel ID
    fallback_model_id: Optional[str] = None # 关联 ModelLevel ID
    sub_agent_ids: List[str] = Field(default_factory=list)  # 关联 SubAgent ID列表
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SubAgentModel(BaseModel):
    """子Agent"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    name: str
    description: Optional[str] = None
    system_prompt: str# 独立提示词
    model_id: str                          # 从模型池选，关联 ModelLevel ID
    skill_ids: List[str] = Field(default_factory=list)# 关联 Skill ID 列表
    tool_ids: List[str] = Field(default_factory=list)    # 关联 Tool ID 列表
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SkillModel(BaseModel):
    """技能"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    name: str
    description: str
    tool_ids: List[str] = Field(default_factory=list)# 关联 Tool ID 列表
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class FileProcessingModel(BaseModel):
    """文件处理 - 要素抽取配置"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    file_type: str                         # 保函 / 合同 / 发票 等业务类型
    fields: List[str] = Field(default_factory=list)  # 需要抽取的要素
    prompt: Optional[str] = None           # 自定义提示词，不填用通用模板
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)



class SceneModel(BaseModel):
    """场景配置"""
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[Any] = Field(alias="_id", default=None)
    scene_code: str
    available_role_ids: List[str] = Field(default_factory=list)  # 关联 Role ID 列表
    route_key: Optional[str] = None
    report_config: Optional[Dict[str, Any]] = None  # workflow配置：文件、数据等
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
