# -*- coding: utf-8 -*-
# 文件：app/Schema.py
# time: 2026/3/10

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any, List, Dict
from datetime import datetime, timezone
from langchain_core.callbacks import BaseCallbackHandler
from typing import Optional, List, Dict, Any

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., description="用户输入")
    app_id: str = Field(..., min_length=1, description="应用 ID（必填）")
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

class GatewayAppCreateRequest(BaseModel):
    app_name: str = Field(..., description="应用名称")
    available_scenes: List[Dict[str, Any]] = Field(default_factory=list, description="可用场景及功能")
    description: str = Field(default=None,description="描述")


class ModelConnectionCreateRequest(BaseModel):
    protocol: str = Field(..., description="渠道协议，如 openai / deepseek / aliyun")
    base_url: str = Field(..., description="模型服务基础地址")
    api_key: str = Field(..., description="模型服务密钥")
    description: Optional[str] = Field(default=None, description="连接描述")
    models: Optional[List[str]] = Field(
        default=None,
        description="可选：手工指定模型列表；不传则由后端自动探测/保持空列表"
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



# ============================================================
# Token & 耗时 收集器
# ============================================================

class UsageCollector(BaseCallbackHandler):
    """
    收集每次 LLM 调用的 token + 模型 + agent(node)
    """
    def __init__(self):
        super().__init__()
        self.total_tokens: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.first_token_time: Optional[datetime] = None

        self.call_details: list[dict[str, Any]] = []
        self._seq: int = 0
        self._current_model: str = "unknown"
        self._current_agent: str = "unknown"

    def on_llm_start(self, serialized, prompts=None, *, invocation_params=None, **kwargs):
        if self.first_token_time is None:
            self.first_token_time = datetime.now(timezone.utc)

        self._seq += 1

        # 1) model 名
        model_name = None
        if invocation_params:
            model_name = invocation_params.get("model") or invocation_params.get("model_name")
        if not model_name and serialized:
            kw = serialized.get("kwargs", {}) if isinstance(serialized, dict) else {}
            model_name = kw.get("model") or kw.get("model_name")
        self._current_model = model_name or "unknown"

        # 2) agent 名（LangGraph 注入）
        metadata = kwargs.get("metadata", {}) or {}
        self._current_agent = metadata.get("langgraph_node", "unknown")

    def on_llm_end(self, response, **kwargs):
        call_prompt = 0
        call_completion = 0
        call_total = 0

        # 优先 llm_output
        try:
            if response and hasattr(response, "llm_output") and response.llm_output:
                usage = response.llm_output.get("token_usage") or response.llm_output.get("usage") or {}
                call_total = usage.get("total_tokens", 0) or 0
                call_prompt = usage.get("prompt_tokens", 0) or 0
                call_completion = usage.get("completion_tokens", 0) or 0
        except Exception:
            pass

        # 兜底 generations
        if call_total == 0:
            try:
                if response and hasattr(response, "generations"):
                    for gen_list in response.generations:
                        for gen in gen_list:
                            info = getattr(gen, "generation_info", None) or {}
                            usage = info.get("token_usage") or info.get("usage") or {}
                            call_total += usage.get("total_tokens", 0) or 0
                            call_prompt += usage.get("prompt_tokens", 0) or 0
                            call_completion += usage.get("completion_tokens", 0) or 0
            except Exception:
                pass

        self.total_tokens += call_total
        self.prompt_tokens += call_prompt
        self.completion_tokens += call_completion

        self.call_details.append({
            "seq": self._seq,
            "agent": self._current_agent,   # 你要的字段
            "model": self._current_model,
            "prompt_tokens": call_prompt,
            "completion_tokens": call_completion,
            "total_tokens": call_total,
        })

    @property
    def final_model(self) -> Optional[str]:
        if not self.call_details:
            return None
        return self.call_details[-1].get("model")

    @property
    def final_agent(self) -> Optional[str]:
        if not self.call_details:
            return None
        return self.call_details[-1].get("agent")
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
