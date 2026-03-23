# -*- coding: utf-8 -*-
from typing import Optional, List, Dict
from datetime import datetime
from .database import Database
from .CRUD import CRUD
from .Schema import (
    ModelConnectionModel, ModelLevelModel,
    GatewayEnvModel, GatewayAppModel, GatewayChannelModel,
    ToolModel, ChatLogModel,
    RoleModel, SubAgentModel, SkillModel,
    FileProcessingModel, SceneModel,
)


class BaseConfigService:
    """配置服务基类，通用CRUD"""

    collection: str = ""
    model_class = None

    def __init__(self):
        self.crud = CRUD(Database.get_session)

    def create(self, data) -> str:
        doc = data.model_dump(by_alias=True, exclude_none=True)
        doc["created_at"] = datetime.now().isoformat()
        doc["updated_at"] = datetime.now().isoformat()
        return self.crud.insert_document(self.collection, doc)

    def get_by_id(self, doc_id: str) -> Optional[Dict]:
        return self.crud.find_one(self.collection, {"_id": doc_id})

    def get_all(self) -> List[Dict]:
        return self.crud.find_documents(self.collection, {})

    def update(self, doc_id: str, update_data: Dict) -> int:
        update_data.pop("_id", None)
        update_data["updated_at"] = datetime.now().isoformat()
        return self.crud.update_document(
            self.collection, {"_id": doc_id}, update_data
        )

    def delete(self, doc_id: str) -> int:
        return self.crud.delete_document(self.collection, {"_id": doc_id})

    def query(self, query: Dict) -> List[Dict]:
        return self.crud.find_documents(self.collection, query)


#============================================================
# 系统配置
# ============================================================

class ModelConnectionService(BaseConfigService):
    collection = "model_connections"
    model_class = ModelConnectionModel

    def get_by_protocol(self, protocol: str) -> List[Dict]:
        return self.query({"protocol": protocol})


class ModelLevelService(BaseConfigService):
    collection = "model_levels"
    model_class = ModelLevelModel

    def get_by_level(self, level: int) -> List[Dict]:
        return self.query({"level": str(level)})

    def get_by_connection(self, connection_id: str) -> List[Dict]:
        return self.query({"connection_id": connection_id})

    def get_fallback_chain(self) -> List[Dict]:
        return self.crud.find_documents(
            self.collection, {}, sort_by="level", ascending=True, sort_as_number=True
        )



class GatewayEnvService(BaseConfigService):
    collection = "gateway_env"
    model_class = GatewayEnvModel

    def get_current(self) -> Optional[Dict]:
        """网关环境只有一条记录"""
        results = self.get_all()
        return results[0] if results else None

    def save(self, data: GatewayEnvModel) -> str:
        current = self.get_current()
        if current:
            self.update(current["_id"], data.model_dump(exclude_none=True, exclude={"id"}))
            return current["_id"]
        return self.create(data)


class GatewayAppService(BaseConfigService):
    collection = "gateway_apps"
    model_class = GatewayAppModel

    def get_by_app_id(self, app_id: str) -> Optional[Dict]:
        return self.crud.find_one(self.collection, {"app_id": app_id})

    def validate_token(self, app_id: str, token: str) -> bool:
        app = self.get_by_app_id(app_id)
        if not app:
            return False
        return app.get("auth_token") == token


class GatewayChannelService(BaseConfigService):
    collection = "gateway_channels"
    model_class = GatewayChannelModel

    def get_by_channel(self, channel: str) -> Optional[Dict]:
        return self.crud.find_one(self.collection, {"channel": channel})

    def get_enabled_channels(self) -> List[Dict]:
        return self.query({"enabled": "true"})


class ToolService(BaseConfigService):
    collection = "tools"
    model_class = ToolModel

    def get_by_type(self, tool_type: str) -> List[Dict]:
        return self.query({"type": tool_type})

    def get_enabled(self) -> List[Dict]:
        return self.query({"enabled": "true"})

    def get_by_ids(self, tool_ids: List[str]) -> List[Dict]:
        return self.crud.find_documents(
            self.collection, {"_id": {"$in": tool_ids}}
        )


class ChatLogService(BaseConfigService):
    collection = "chat_logs"
    model_class = ChatLogModel

    def log(self, data: ChatLogModel) -> str:
        return self.create(data)

    def get_by_session(self, session_id: str) -> List[Dict]:
        return self.crud.find_documents(
            self.collection,
            {"session_id": session_id},
            sort_by="request_time",
            ascending=True
        )

    def get_by_app(self, app_id: str, limit: int = 100) -> List[Dict]:
        return self.crud.find_documents(
            self.collection,
            {"app_id": app_id},
            sort_by="request_time",
            ascending=False,
            limit=limit
        )


# ============================================================
# 业务配置
# ============================================================

class RoleService(BaseConfigService):
    collection = "roles"
    model_class = RoleModel

    def add_sub_agent(self, role_id: str, sub_agent_id: str) -> int:
        role = self.get_by_id(role_id)
        if not role:
            return 0
        sub_agent_ids = role.get("sub_agent_ids", [])
        if sub_agent_id not in sub_agent_ids:
            sub_agent_ids.append(sub_agent_id)
            return self.update(role_id, {"sub_agent_ids": sub_agent_ids})
        return 0

    def remove_sub_agent(self, role_id: str, sub_agent_id: str) -> int:
        role = self.get_by_id(role_id)
        if not role:
            return 0
        sub_agent_ids = role.get("sub_agent_ids", [])
        if sub_agent_id in sub_agent_ids:
            sub_agent_ids.remove(sub_agent_id)
            return self.update(role_id, {"sub_agent_ids": sub_agent_ids})
        return 0


class SubAgentService(BaseConfigService):
    collection = "sub_agents"
    model_class = SubAgentModel

    def add_skill(self, agent_id: str, skill_id: str) -> int:
        agent = self.get_by_id(agent_id)
        if not agent:
            return 0
        skill_ids = agent.get("skill_ids", [])
        if skill_id not in skill_ids:
            skill_ids.append(skill_id)
            return self.update(agent_id, {"skill_ids": skill_ids})
        return 0

    def remove_skill(self, agent_id: str, skill_id: str) -> int:
        agent = self.get_by_id(agent_id)
        if not agent:
            return 0
        skill_ids = agent.get("skill_ids", [])
        if skill_id in skill_ids:
            skill_ids.remove(skill_id)
            return self.update(agent_id, {"skill_ids": skill_ids})
        return 0

    def add_tool(self, agent_id: str, tool_id: str) -> int:
        agent = self.get_by_id(agent_id)
        if not agent:
            return 0
        tool_ids = agent.get("tool_ids", [])
        if tool_id not in tool_ids:
            tool_ids.append(tool_id)
            return self.update(agent_id, {"tool_ids": tool_ids})
        return 0

    def remove_tool(self, agent_id: str, tool_id: str) -> int:
        agent = self.get_by_id(agent_id)
        if not agent:
            return 0
        tool_ids = agent.get("tool_ids", [])
        if tool_id in tool_ids:
            tool_ids.remove(tool_id)
            return self.update(agent_id, {"tool_ids": tool_ids})
        return 0


class SkillService(BaseConfigService):
    collection = "skills"
    model_class = SkillModel

    def add_tool(self, skill_id: str, tool_id: str) -> int:
        skill = self.get_by_id(skill_id)
        if not skill:
            return 0
        tool_ids = skill.get("tool_ids", [])
        if tool_id not in tool_ids:
            tool_ids.append(tool_id)
            return self.update(skill_id, {"tool_ids": tool_ids})
        return 0

    def remove_tool(self, skill_id: str, tool_id: str) -> int:
        skill = self.get_by_id(skill_id)
        if not skill:
            return 0
        tool_ids = skill.get("tool_ids", [])
        if tool_id in tool_ids:
            tool_ids.remove(tool_id)
            return self.update(skill_id, {"tool_ids": tool_ids})
        return 0


class FileProcessingService(BaseConfigService):
    collection = "file_processing"
    model_class = FileProcessingModel

    def get_by_file_type(self, file_type: str) -> Optional[Dict]:
        return self.crud.find_one(self.collection, {"file_type": file_type})


class SceneService(BaseConfigService):
    collection = "scenes"
    model_class = SceneModel

    def get_by_code(self, scene_code: str) -> Optional[Dict]:
        return self.crud.find_one(self.collection, {"scene_code": scene_code})

    def add_role(self, scene_id: str, role_id: str) -> int:
        scene = self.get_by_id(scene_id)
        if not scene:
            return 0
        role_ids = scene.get("available_role_ids", [])
        if role_id not in role_ids:
            role_ids.append(role_id)
            return self.update(scene_id, {"available_role_ids": role_ids})
        return 0

    def remove_role(self, scene_id: str, role_id: str) -> int:
        scene = self.get_by_id(scene_id)
        if not scene:
            return 0
        role_ids = scene.get("available_role_ids", [])
        if role_id in role_ids:
            role_ids.remove(role_id)
            return self.update(scene_id, {"available_role_ids": role_ids})
        return 0
