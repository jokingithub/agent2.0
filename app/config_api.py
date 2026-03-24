# -*- coding: utf-8 -*-
import secrets
from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional
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
    available_scenes: List[str] = Field(default_factory=list, description="可用场景")


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

@router.get("/tools/enabled", summary="获取所有启用的工具")
def get_enabled_tools():
    return _tool_service.get_enabled()

@router.get("/tools/type/{tool_type}", summary="按类型查工具")
def get_tools_by_type(tool_type: str):
    return _tool_service.get_by_type(tool_type)


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
# 通用工厂：为每个配置生成标准CRUD接口
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
        @router.post(f"/{path}", summary=f"创建{name}")
        def create(data: Dict):
            model = model_class(**dict(data))
            doc_id = service.create(model)
            return {"id": doc_id, "message": f"{name}创建成功"}

    @router.put(f"/{path}/{{doc_id}}", summary=f"更新{name}")
    def update(doc_id: str, data: Dict):
        count = service.update(doc_id, data)
        if count == 0:
            raise HTTPException(status_code=404, detail=f"{name}不存在")
        return {"message": f"{name}更新成功"}

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

