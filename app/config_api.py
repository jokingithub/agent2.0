# -*- coding: utf-8 -*-
import asyncio
import os
import secrets
import httpx
from fastapi import APIRouter, HTTPException, Path as ApiPath
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, create_model
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
from app.Schema import (
    GatewayAppCreateRequest,ModelConnectionCreateRequest,ModelConnectionUpdateRequest,
    MCPToolSyncRequest,
    WhitelistReplaceRequest,
    WhitelistItemRequest,
)
from logger import logger
from pathlib import Path as FilePath
from collections import deque
from config import Config


router = APIRouter(prefix="/config", tags=["配置管理"])



# ============================================================
# 特殊接口（非标准CRUD）
# ============================================================

# --- 系统日志 ---
def _resolve_log_file(file_name: str = "app.log") -> FilePath:
    """
    解析日志文件路径：
    - Config.LOG_FILE_PATH 若为相对路径，按项目根目录拼接
    - file_name 仅允许 app.log*，防止路径穿越
    """
    base_name = (file_name or "app.log").strip()

    # 只允许读取 app.log / app.log.1 / app.log.2 ...
    if not base_name.startswith("app.log") or "/" in base_name or "\\" in base_name:
        raise HTTPException(status_code=400, detail="非法日志文件名")

    project_root = FilePath(__file__).resolve().parents[1]  # agent2.0/
    configured = FilePath(Config.LOG_FILE_PATH)

    log_path = configured if configured.is_absolute() else (project_root / configured)
    log_dir = log_path.parent

    target = log_dir / base_name
    return target


def _tail_lines(path: FilePath, n: int) -> list[str]:
    if n <= 0:
        return []
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        return [line.rstrip("\n") for line in deque(f, maxlen=n)]


@router.get("/system-logs/files", summary="获取系统日志文件列表")
def list_system_log_files():
    """
    返回 logs 目录下可读的 app.log* 文件（按修改时间倒序）
    """
    project_root = FilePath(__file__).resolve().parents[1]
    configured = FilePath(Config.LOG_FILE_PATH)
    log_path = configured if configured.is_absolute() else (project_root / configured)
    log_dir = log_path.parent

    if not log_dir.exists():
        return {"files": []}

    files = []
    for p in log_dir.glob("app.log*"):
        if p.is_file():
            stat = p.stat()
            files.append({
                "name": p.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })

    files.sort(key=lambda x: x["mtime"], reverse=True)
    return {"files": files}


@router.get("/system-logs", summary="读取系统日志（tail）")
def get_system_logs(
    file: str = "app.log",
    tail: int = 200,
    level: Optional[str] = None,
    keyword: Optional[str] = None,
):
    """
    tail: 返回最后 N 行（1~2000）
    level: 可选过滤，如 INFO/WARNING/ERROR/DEBUG
    keyword: 可选关键字过滤
    """
    if tail < 1:
        tail = 1
    if tail > 2000:
        tail = 2000

    path = _resolve_log_file(file)
    lines = _tail_lines(path, tail)

    level_upper = (level or "").strip().upper()
    kw = (keyword or "").strip().lower()

    if level_upper:
        lines = [x for x in lines if level_upper in x.upper()]
    if kw:
        lines = [x for x in lines if kw in x.lower()]

    return {
        "file": path.name,
        "exists": path.exists(),
        "count": len(lines),
        "lines": lines,
    }

# --- 网关环境（单例） ---
_gateway_env_service = GatewayEnvService()


def _normalize_origin(origin: str) -> str:
    value = (origin or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="origin 不能为空")
    if value == "*":
        return value
    if not (value.startswith("http://") or value.startswith("https://")):
        raise HTTPException(status_code=400, detail="origin 必须以 http:// 或 https:// 开头，或使用 *")
    return value.rstrip("/")


def _dedup_keep_order(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def _save_whitelist(new_whitelist: List[str]) -> Dict[str, Any]:
    current = _gateway_env_service.get_current() or {}
    model = GatewayEnvModel(
        port=int(current.get("port", 8000)),
        whitelist=new_whitelist,
    )
    doc_id = _gateway_env_service.save(model)
    return {
        "id": doc_id,
        "port": model.port,
        "whitelist": model.whitelist,
    }

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


@router.get("/gateway-env/whitelist", summary="获取白名单")
def get_gateway_whitelist():
    current = _gateway_env_service.get_current() or {}
    whitelist = current.get("whitelist") or []
    if not isinstance(whitelist, list):
        whitelist = []
    return {"whitelist": whitelist}


@router.put("/gateway-env/whitelist", summary="替换白名单")
def replace_gateway_whitelist(data: WhitelistReplaceRequest):
    normalized = _dedup_keep_order([_normalize_origin(x) for x in data.whitelist])
    return _save_whitelist(normalized)


@router.post("/gateway-env/whitelist", summary="新增白名单项")
def add_gateway_whitelist_item(data: WhitelistItemRequest):
    current = _gateway_env_service.get_current() or {}
    existing = current.get("whitelist") or []
    if not isinstance(existing, list):
        existing = []

    target = _normalize_origin(data.origin)
    if target in existing:
        return {
            "message": "白名单项已存在",
            "whitelist": existing,
        }

    existing.append(target)
    normalized = _dedup_keep_order(existing)
    result = _save_whitelist(normalized)
    result["message"] = "白名单项新增成功"
    return result


@router.delete("/gateway-env/whitelist", summary="删除白名单项")
def remove_gateway_whitelist_item(origin: str):
    target = _normalize_origin(origin)

    current = _gateway_env_service.get_current() or {}
    existing = current.get("whitelist") or []
    if not isinstance(existing, list):
        existing = []

    if target not in existing:
        raise HTTPException(status_code=404, detail="白名单项不存在")

    new_whitelist = [x for x in existing if x != target]
    result = _save_whitelist(new_whitelist)
    result["message"] = "白名单项删除成功"
    return result


# --- 网关鉴权验证 ---
_gateway_app_service = GatewayAppService()

@router.post("/gateway-apps/validate", summary="验证AppId和Token")
def validate_app_token(app_id: str, token: str):
    valid = _gateway_app_service.validate_token(app_id, token)
    return {"valid": valid}


@router.post("/gateway-apps", summary="创建外部调用配置")
def create_gateway_app(data: GatewayAppCreateRequest):
    payload = data.model_dump()
    payload["app_id"] = f"app_{secrets.token_hex(8)}"
    payload["auth_token"] = secrets.token_urlsafe(32)
    payload["description"] = None if not data.description else data.description

    model = GatewayAppModel(**payload)
    doc_id = _gateway_app_service.create(model)
    return {
        "app_name": payload["app_name"],
        "app_id": payload["app_id"],
        "auth_token": payload["auth_token"],
        "description": payload["description"],
        "message": "外部调用配置创建成功",
    }


# --- 模型降级链 ---
_model_level_service = ModelLevelService()
_model_connection_service = ModelConnectionService()


def _extract_model_names(payload: Any) -> List[str]:
    """从不同模型接口返回结构中提取模型名称列表。"""
    model_names: List[str] = []

    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            source = payload.get("data")
        elif isinstance(payload.get("models"), list):
            source = payload.get("models")
        else:
            source = []
    elif isinstance(payload, list):
        source = payload
    else:
        source = []

    for item in source:
        if isinstance(item, dict):
            name = item.get("id") or item.get("model") or item.get("name")
            if name:
                model_names.append(str(name))
        elif isinstance(item, str):
            model_names.append(item)

    # 去重并保持顺序
    uniq: List[str] = []
    seen = set()
    for m in model_names:
        if m not in seen:
            seen.add(m)
            uniq.append(m)
    return uniq


async def _fetch_models_from_connection(base_url: str, api_key: str, protocol: str = "") -> List[str]:
    """根据模型连接信息自动拉取可用模型列表（OpenAI兼容优先）。"""
    base = (base_url or "").rstrip("/")
    if not base:
        raise ValueError("base_url 不能为空")

    headers_candidates = [
        {"Authorization": f"Bearer {api_key}"},
        {"api-key": api_key},
        {"x-api-key": api_key},
    ]

    errors: List[str] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for headers in headers_candidates:
            try:
                resp = await client.get(f"{base}/models", headers=headers)
                if resp.status_code >= 400:
                    errors.append(f"{resp.status_code}: {resp.text[:200]}")
                    continue

                payload = resp.json()
                models = _extract_model_names(payload)
                if models:
                    return models

                errors.append("返回成功但未解析到模型列表")
            except Exception as e:
                errors.append(str(e))

    detail = " | ".join(errors[:3]) if errors else "未知错误"
    logger.warning(f"自动拉取模型失败 protocol={protocol}, base_url={base}, detail={detail}")
    raise RuntimeError(f"自动拉取模型失败：{detail}")

@router.post("/model-connections", summary="创建模型连接（先校验连通性）")
def create_model_connection(data: ModelConnectionCreateRequest):
    try:
        fetched_models = asyncio.run(
            _fetch_models_from_connection(
                base_url=data.base_url,
                api_key=data.api_key,
                protocol=data.protocol,
            )
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"模型连接不可用：{e}")

    models = (getattr(data, "models", None) or [])
    if not models:
        models = fetched_models

    model = ModelConnectionModel(
        protocol=data.protocol,
        base_url=data.base_url,
        api_key=data.api_key,
        models=models,
        description=data.description,
    )
    doc_id = _model_connection_service.create(model)
    return {
        "id": doc_id,
        "models_count": len(models),
        "message": "模型连接创建成功（已校验连通性）",
    }


@router.put("/model-connections/{doc_id}", summary="更新模型连接（连接参数变更时校验连通性）")
def update_model_connection(doc_id: str, data: ModelConnectionUpdateRequest):
    current = _model_connection_service.get_by_id(doc_id)
    if not current:
        raise HTTPException(status_code=404, detail="模型连接不存在")

    protocol = data.protocol if data.protocol is not None else current.get("protocol", "")
    base_url = data.base_url if data.base_url is not None else current.get("base_url", "")
    api_key = data.api_key if data.api_key is not None else current.get("api_key", "")

    need_validate = (
        data.protocol is not None
        or data.base_url is not None
        or data.api_key is not None
    )
    if need_validate:
        try:
            asyncio.run(
                _fetch_models_from_connection(
                    base_url=base_url,
                    api_key=api_key,
                    protocol=protocol,
                )
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"模型连接不可用：{e}")

    update_data = {}
    if data.protocol is not None:
        update_data["protocol"] = data.protocol
    if data.base_url is not None:
        update_data["base_url"] = data.base_url
    if data.api_key is not None:
        update_data["api_key"] = data.api_key
    if data.description is not None:
        update_data["description"] = data.description
    if getattr(data, "models", None) is not None:
        update_data["models"] = data.models

    if not update_data:
        return {"message": "无更新字段"}

    _model_connection_service.update(doc_id, update_data)
    return {
        "message": "模型连接更新成功",
    }

# @router.post("/model-connections", summary="创建模型连接（自动拉取模型列表）")
# def create_model_connection(data: ModelConnectionCreateRequest):
#     try:
#         models = asyncio.run(
#             _fetch_models_from_connection(
#                 base_url=data.base_url,
#                 api_key=data.api_key,
#                 protocol=data.protocol,
#             )
#         )
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

#     model = ModelConnectionModel(
#         protocol=data.protocol,
#         base_url=data.base_url,
#         api_key=data.api_key,
#         models=models,
#         description=data.description,
#     )
#     doc_id = _model_connection_service.create(model)
#     return {
#         "id": doc_id,
#         "models_count": len(models),
#         "models": models,
#         "message": "模型连接创建成功（已自动同步模型列表）",
#     }


# @router.put("/model-connections/{doc_id}", summary="更新模型连接（自动刷新模型列表）")
# def update_model_connection(doc_id: str, data: ModelConnectionUpdateRequest):
#     current = _model_connection_service.get_by_id(doc_id)
#     if not current:
#         raise HTTPException(status_code=404, detail="模型连接不存在")

#     protocol = data.protocol if data.protocol is not None else current.get("protocol", "")
#     base_url = data.base_url if data.base_url is not None else current.get("base_url", "")
#     api_key = data.api_key if data.api_key is not None else current.get("api_key", "")
#     description = data.description if data.description is not None else current.get("description")

#     # 优先允许手工指定；否则在连接信息变化或当前模型列表为空时自动刷新
#     if data.models is not None:
#         models = data.models
#     else:
#         need_refresh = (
#             data.protocol is not None
#             or data.base_url is not None
#             or data.api_key is not None
#             or not current.get("models")
#         )
#         if need_refresh:
#             try:
#                 models = asyncio.run(
#                     _fetch_models_from_connection(
#                         base_url=base_url,
#                         api_key=api_key,
#                         protocol=protocol,
#                     )
#                 )
#             except Exception as e:
#                 raise HTTPException(status_code=400, detail=str(e))
#         else:
#             models = current.get("models", [])

#     update_data = {
#         "protocol": protocol,
#         "base_url": base_url,
#         "api_key": api_key,
#         "description": description,
#         "models": models,
#     }
#     _model_connection_service.update(doc_id, update_data)

#     return {
#         "message": "模型连接更新成功",
#         "models_count": len(models),
#         "models": models,
#     }

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

@router.get("/chat-logs", summary="查询会话日志（可选按 app_id / session_id 过滤）")
def list_chat_logs(app_id: Optional[str] = None, session_id: Optional[str] = None, limit: int = 200):
    if session_id:
        rows = _chat_log_service.get_by_session(session_id)
    elif app_id:
        rows = _chat_log_service.get_by_app(app_id, limit)
    else:
        rows = _chat_log_service.get_all()

    # 统一按 request_time 倒序，且限制返回数量
    def _ts(x):
        return x.get("request_time") or ""
    rows = sorted(rows, key=_ts, reverse=True)

    if limit and limit > 0:
        rows = rows[:limit]

    return rows



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
    update_enabled: bool = True,
    lookup_field: str = "_id",
    lookup_param: str = "doc_id",
):
    service = service_class()

    def _build_request_model(mc, model_name: str, partial: bool = False):
        """为请求体动态生成模型，屏蔽只读字段。"""
        readonly_fields = {"id", "created_at", "updated_at"}
        fields: Dict[str, Any] = {}

        for fname, finfo in mc.model_fields.items():
            if fname in readonly_fields:
                continue

            if partial:
                fields[fname] = (Optional[finfo.annotation], None)
            else:
                if finfo.is_required():
                    fields[fname] = (finfo.annotation, ...)
                elif finfo.default_factory is not None:
                    fields[fname] = (finfo.annotation, Field(default_factory=finfo.default_factory))
                else:
                    fields[fname] = (finfo.annotation, finfo.default)

        return create_model(model_name, **fields)

    @router.get(f"/{path}", summary=f"获取所有{name}")
    def get_all():
        return service.get_all()

    @router.get(f"/{path}/{{{lookup_param}}}", summary=f"获取单个{name}")
    def get_one(lookup_value: str = ApiPath(..., alias=lookup_param)):
        if lookup_field == "_id":
            result = service.get_by_id(lookup_value)
        else:
            rows = service.query({lookup_field: lookup_value})
            result = rows[0] if rows else None
        if not result:
            raise HTTPException(status_code=404, detail=f"{name}不存在")
        return result

    if create_enabled:
        # 用闭包捕获 model_class，让 FastAPI 能读到字段定义
        def make_create(mc, svc, label):
            create_req_model = _build_request_model(mc, f"{mc.__name__}CreateRequestAuto", partial=False)

            @router.post(f"/{path}", summary=f"创建{label}")
            def create(data):
                doc_id = svc.create(data)
                return {"id": doc_id, "message": f"{label}创建成功"}
            create.__annotations__["data"] = create_req_model
            return create
        make_create(model_class, service, name)

    if update_enabled:
        # update 也一样，用 model_class 替代 Dict
        def make_update(mc, svc, label):
            update_req_model = _build_request_model(mc, f"{mc.__name__}UpdateRequestAuto", partial=True)

            @router.put(f"/{path}/{{{lookup_param}}}", summary=f"更新{label}")
            def update(lookup_value: str = ApiPath(..., alias=lookup_param), data = ...):
                update_dict = data.model_dump(
                    exclude_none=True,
                    exclude={"id", "created_at", "updated_at"}
                )
                if lookup_field == "_id":
                    count = svc.update(lookup_value, update_dict)
                else:
                    rows = svc.query({lookup_field: lookup_value})
                    target = rows[0] if rows else None
                    count = svc.update(target["_id"], update_dict) if target else 0
                if count == 0:
                    raise HTTPException(status_code=404, detail=f"{label}不存在")
                return {"message": f"{label}更新成功"}
            update.__annotations__["data"] = update_req_model
            return update
        make_update(model_class, service, name)

    @router.delete(f"/{path}/{{{lookup_param}}}", summary=f"删除{name}")
    def delete(lookup_value: str = ApiPath(..., alias=lookup_param)):
        if lookup_field == "_id":
            count = service.delete(lookup_value)
        else:
            rows = service.query({lookup_field: lookup_value})
            target = rows[0] if rows else None
            count = service.delete(target["_id"]) if target else 0
        if count == 0:
            raise HTTPException(status_code=404, detail=f"{name}不存在")
        return {"message": f"{name}删除成功"}



# 注册所有配置的CRUD路由
register_crud_routes(
    "model-connections",
    ModelConnectionService,
    ModelConnectionModel,
    "模型连接",
    create_enabled=False,
    update_enabled=False,
)
register_crud_routes("model-levels", ModelLevelService, ModelLevelModel, "模型分级")
register_crud_routes(
    "gateway-apps",
    GatewayAppService,
    GatewayAppModel,
    "外部调用配置",
    create_enabled=False,
    lookup_field="app_id",
    lookup_param="app_id",
)
register_crud_routes("gateway-channels", GatewayChannelService, GatewayChannelModel, "渠道配置")
register_crud_routes("tools", ToolService, ToolModel, "工具")
register_crud_routes("roles", RoleService, RoleModel, "角色")
register_crud_routes("sub-agents", SubAgentService, SubAgentModel, "子Agent")
register_crud_routes("skills", SkillService, SkillModel, "技能")
register_crud_routes("file-processing", FileProcessingService, FileProcessingModel, "文件处理")
register_crud_routes("scenes", SceneService, SceneModel, "场景")

