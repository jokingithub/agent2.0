# -*- coding: utf-8 -*-
import asyncio
import os
import secrets
from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from dataBase.ConfigService import (
    ModelConnectionService, ModelLevelService,
    GatewayEnvService, GatewayAppService, GatewayChannelService,
    ToolService, ChatLogService,
    RoleService, SubAgentService, SkillService,
    FileProcessingService, SceneService,
)
from dataBase.Schema import (
    ModelConnectionModel, ModelLevelModel,
    GatewayEnvModel, GatewayAppModel, GatewayChannelModel,
    ToolModel, ChatLogModel,
    RoleModel, SubAgentModel, SkillModel,
    FileProcessingModel, SceneModel,
)

router = APIRouter(prefix="/config", tags=["配置管理"])


class GatewayAppCreateRequest(BaseModel):
    app_id: str = Field(..., description="应用ID")
    available_scenes: List[Dict[str, Any]] = Field(default_factory=list, description="可用场景及功能")



class MCPToolSyncRequest(BaseModel):
    url: Optional[str] = Field(default=None, description="MCP SSE地址，如 http://127.0.0.1:9001/sse")
    default_category: str = Field(default="mcp", description="当远端工具未提供分类时使用的默认分类")
    dry_run: bool = Field(default=False, description="仅预览，不写入数据库")
    prune_missing: bool = Field(default=False, description="是否自动下线远端已不存在的本地MCP工具")


# ============================================================
# 特殊接口（非标准CRUD）
# ============================================================

# --- 网关环境（单例） ---
_gateway_env_service = GatewayEnvService()

@router.get("/gateway-env", summary="获取网关环境配置")
def get_gateway_env():
    result = _gateway_env_service.get_current()
    if not result:
        return {"port": 8000, "whitelist": []}
    return result

@router.put("/gateway-env", summary="更新网关环境配置")
def update_gateway_env(data: GatewayEnvModel):
    doc_id = _gateway_env_service.save(data)
    return {"id": doc_id, "message": "网关环境配置更新成功"}


# --- 网关鉴权验证 ---
_gateway_app_service = GatewayAppService()

@router.post("/gateway-apps/validate", summary="验证AppId和Token")
def validate_app_token(app_id: str, token: str):
    valid = _gateway_app_service.validate_token(app_id, token)
    return {"valid": valid}


@router.post("/gateway-apps", summary="创建外部调用配置")
def create_gateway_app(data: GatewayAppCreateRequest):
    payload = data.model_dump()
    payload["auth_token"] = secrets.token_urlsafe(32)

    model = GatewayAppModel(**payload)
    doc_id = _gateway_app_service.create(model)
    return {
        "id": doc_id,
        "app_id": payload["app_id"],
        "auth_token": payload["auth_token"],
        "message": "外部调用配置创建成功",
    }


# --- 模型降级链 ---
_model_level_service = ModelLevelService()

@router.get("/model-levels/fallback-chain", summary="获取模型降级链")
def get_fallback_chain():
    return _model_level_service.get_fallback_chain()


# --- 工具查询 ---
_tool_service = ToolService()


def _extract_arg_name_from_schema(input_schema: Any) -> str:
    """从 MCP input schema 中尽可能提取首个参数名。"""
    if not isinstance(input_schema, dict):
        return "query"

    props = input_schema.get("properties")
    if isinstance(props, dict) and props:
        return str(next(iter(props.keys())))

    required = input_schema.get("required")
    if isinstance(required, list) and required:
        return str(required[0])

    return "query"


async def _fetch_mcp_tools(url: str) -> List[Dict[str, Any]]:
    """从 MCP 服务拉取工具清单。兼容不同客户端返回结构。"""
    from fastmcp import Client

    # fastmcp 版本兼容：新版本可能没有 Client.from_url
    if hasattr(Client, "from_url"):
        client_ctx = Client.from_url(url)
    else:
        client_ctx = Client(url)

    async with client_ctx as client:
        if hasattr(client, "list_tools"):
            tools_resp = await client.list_tools()
        elif hasattr(client, "get_tools"):
            tools_resp = await client.get_tools()
        else:
            raise RuntimeError("当前 fastmcp Client 不支持 list_tools/get_tools")

    # 兼容：直接 list，或对象里带 tools 字段
    if isinstance(tools_resp, list):
        raw_tools = tools_resp
    elif hasattr(tools_resp, "tools"):
        raw_tools = getattr(tools_resp, "tools") or []
    elif isinstance(tools_resp, dict) and isinstance(tools_resp.get("tools"), list):
        raw_tools = tools_resp.get("tools")
    else:
        raw_tools = []

    result: List[Dict[str, Any]] = []
    for item in raw_tools:
        if isinstance(item, dict):
            name = item.get("name")
            description = item.get("description", "")
            input_schema = item.get("inputSchema") or item.get("input_schema") or {}
        else:
            name = getattr(item, "name", None)
            description = getattr(item, "description", "")
            input_schema = (
                getattr(item, "inputSchema", None)
                or getattr(item, "input_schema", None)
                or {}
            )

        if not name:
            continue

        result.append(
            {
                "name": str(name),
                "description": str(description or ""),
                "arg_name": _extract_arg_name_from_schema(input_schema),
            }
        )

    return result

@router.get("/tools/enabled", summary="获取所有启用的工具")
def get_enabled_tools():
    return _tool_service.get_enabled()

@router.get("/tools/type/{tool_type}", summary="按类型查工具")
def get_tools_by_type(tool_type: str):
    return _tool_service.get_by_type(tool_type)


@router.post("/tools/sync-from-mcp", summary="从MCP服务扫描并同步工具")
def sync_tools_from_mcp(data: MCPToolSyncRequest):
    url = data.url or os.getenv("MCP_SYNC_URL") or "http://127.0.0.1:9001/sse"

    try:
        mcp_tools = asyncio.run(_fetch_mcp_tools(url))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取MCP工具失败: {e}")

    remote_tool_names = {t["name"] for t in mcp_tools}

    if data.dry_run:
        stale_tools = []
        if data.prune_missing:
            local_mcp_tools = _tool_service.query({"type": "mcp", "url": url})
            stale_tools = [
                {"id": x.get("_id"), "name": x.get("name")}
                for x in local_mcp_tools
                if x.get("name") not in remote_tool_names and x.get("enabled", True)
            ]
        return {
            "message": "预览成功（未写库）",
            "url": url,
            "count": len(mcp_tools),
            "tools": mcp_tools,
            "prune_missing": data.prune_missing,
            "stale_tools": stale_tools,
        }

    synced = []
    for t in mcp_tools:
        payload = {
            "name": t["name"],
            "type": "mcp",
            "category": data.default_category,
            "url": url,
            "enabled": True,
            "description": t.get("description", ""),
            "config": {
                "remote_tool_name": t["name"],
                "arg_name": t.get("arg_name", "query"),
                "expose_to_agent": True,
            },
        }
        doc_id = _tool_service.upsert_mcp_tool(payload)
        synced.append({"id": doc_id, "name": t["name"]})

    disabled = []
    if data.prune_missing:
        local_mcp_tools = _tool_service.query({"type": "mcp", "url": url})
        for x in local_mcp_tools:
            if x.get("name") not in remote_tool_names and x.get("enabled", True):
                _tool_service.update(x["_id"], {"enabled": False})
                disabled.append({"id": x.get("_id"), "name": x.get("name")})

    return {
        "message": "MCP工具同步完成",
        "url": url,
        "count": len(synced),
        "tools": synced,
        "prune_missing": data.prune_missing,
        "disabled_count": len(disabled),
        "disabled_tools": disabled,
    }


# --- 会话日志 ---
_chat_log_service = ChatLogService()

@router.get("/chat-logs/session/{session_id}", summary="按会话查日志")
def get_logs_by_session(session_id: str):
    return _chat_log_service.get_by_session(session_id)

@router.get("/chat-logs/app/{app_id}", summary="按应用查日志")
def get_logs_by_app(app_id: str, limit: int = 100):
    return _chat_log_service.get_by_app(app_id, limit)


# --- 场景查询 ---
_scene_service = SceneService()

@router.get("/scenes/code/{scene_code}", summary="按场景码查场景")
def get_scene_by_code(scene_code: str):
    result = _scene_service.get_by_code(scene_code)
    if not result:
        raise HTTPException(status_code=404, detail="场景不存在")
    return result


# --- 关联管理：角色 ↔ 子Agent ---
_role_service = RoleService()

@router.post("/roles/{role_id}/sub-agents/{sub_agent_id}", summary="角色添加子Agent")
def role_add_sub_agent(role_id: str, sub_agent_id: str):
    _role_service.add_sub_agent(role_id, sub_agent_id)
    return {"message": "添加成功"}

@router.delete("/roles/{role_id}/sub-agents/{sub_agent_id}", summary="角色移除子Agent")
def role_remove_sub_agent(role_id: str, sub_agent_id: str):
    _role_service.remove_sub_agent(role_id, sub_agent_id)
    return {"message": "移除成功"}


# --- 关联管理：子Agent ↔ 技能/工具 ---
_sub_agent_service = SubAgentService()

@router.post("/sub-agents/{agent_id}/skills/{skill_id}", summary="子Agent添加技能")
def agent_add_skill(agent_id: str, skill_id: str):
    _sub_agent_service.add_skill(agent_id, skill_id)
    return {"message": "添加成功"}

@router.delete("/sub-agents/{agent_id}/skills/{skill_id}", summary="子Agent移除技能")
def agent_remove_skill(agent_id: str, skill_id: str):
    _sub_agent_service.remove_skill(agent_id, skill_id)
    return {"message": "移除成功"}

@router.post("/sub-agents/{agent_id}/tools/{tool_id}", summary="子Agent添加工具")
def agent_add_tool(agent_id: str, tool_id: str):
    _sub_agent_service.add_tool(agent_id, tool_id)
    return {"message": "添加成功"}

@router.delete("/sub-agents/{agent_id}/tools/{tool_id}", summary="子Agent移除工具")
def agent_remove_tool(agent_id: str, tool_id: str):
    _sub_agent_service.remove_tool(agent_id, tool_id)
    return {"message": "移除成功"}

# --- 关联管理：技能 ↔ 工具 ---
_skill_service = SkillService()

@router.post("/skills/{skill_id}/tools/{tool_id}", summary="技能添加工具")
def skill_add_tool(skill_id: str, tool_id: str):
    _skill_service.add_tool(skill_id, tool_id)
    return {"message": "添加成功"}

@router.delete("/skills/{skill_id}/tools/{tool_id}", summary="技能移除工具")
def skill_remove_tool(skill_id: str, tool_id: str):
    _skill_service.remove_tool(skill_id, tool_id)
    return {"message": "移除成功"}


# --- 关联管理：场景 ↔ 角色 ---

@router.post("/scenes/{scene_id}/roles/{role_id}", summary="场景添加角色")
def scene_add_role(scene_id: str, role_id: str):
    _scene_service.add_role(scene_id, role_id)
    return {"message": "添加成功"}

@router.delete("/scenes/{scene_id}/roles/{role_id}", summary="场景移除角色")
def scene_remove_role(scene_id: str, role_id: str):
    _scene_service.remove_role(scene_id, role_id)
    return {"message": "移除成功"}

# ============================================================
# 工厂：根据每个配置生成CRUD接口
# ============================================================

def register_crud_routes(
    path: str,
    service_class,
    model_class,
    name: str,
    create_enabled: bool = True,
):
    service = service_class()

    @router.get(f"/{path}", summary=f"获取所有{name}")
    def get_all():
        return service.get_all()

    @router.get(f"/{path}/{{doc_id}}", summary=f"获取单个{name}")
    def get_one(doc_id: str):
        result = service.get_by_id(doc_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"{name}不存在")
        return result

    if create_enabled:
        # 用闭包捕获 model_class，让 FastAPI 能读到字段定义
        def make_create(mc, svc, label):
            @router.post(f"/{path}", summary=f"创建{label}")
            def create(data: mc):
                doc_id = svc.create(data)
                return {"id": doc_id, "message": f"{label}创建成功"}
            return create
        make_create(model_class, service, name)

    # update 也一样，用 model_class 替代 Dict
    def make_update(mc, svc, label):
        @router.put(f"/{path}/{{doc_id}}", summary=f"更新{label}")
        def update(doc_id: str, data: mc):
            update_dict = data.model_dump(exclude_none=True, exclude={"id"})
            count = svc.update(doc_id, update_dict)
            if count == 0:
                raise HTTPException(status_code=404, detail=f"{label}不存在")
            return {"message": f"{label}更新成功"}
        return update
    make_update(model_class, service, name)

    @router.delete(f"/{path}/{{doc_id}}", summary=f"删除{name}")
    def delete(doc_id: str):
        count = service.delete(doc_id)
        if count == 0:
            raise HTTPException(status_code=404, detail=f"{name}不存在")
        return {"message": f"{name}删除成功"}



# 注册所有配置的CRUD路由
register_crud_routes("model-connections", ModelConnectionService, ModelConnectionModel, "模型连接")
register_crud_routes("model-levels", ModelLevelService, ModelLevelModel, "模型分级")
register_crud_routes("gateway-apps", GatewayAppService, GatewayAppModel, "外部调用配置", create_enabled=False)
register_crud_routes("gateway-channels", GatewayChannelService, GatewayChannelModel, "渠道配置")
register_crud_routes("tools", ToolService, ToolModel, "工具")
register_crud_routes("roles", RoleService, RoleModel, "角色")
register_crud_routes("sub-agents", SubAgentService, SubAgentModel, "子Agent")
register_crud_routes("skills", SkillService, SkillModel, "技能")
register_crud_routes("file-processing", FileProcessingService, FileProcessingModel, "文件处理")
register_crud_routes("scenes", SceneService, SceneModel, "场景")

