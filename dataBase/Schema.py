# -*- coding: utf-8 -*-
# 兼容桩：旧路径 dataBase.Schema -> 新路径 Schema/*
# 后续全量迁移 import 后可删除本文件

from Schema.db_models import (
    FileModel,
    MemoryModel,
    SessionModel,
    ChatLogModel,
    FileTypeModel,
)
from Schema.config_models import (
    ModelConnectionModel,
    ModelLevelModel,
    RoleModel,
    SubAgentModel,
    SkillModel,
    ToolModel,
    FileProcessingModel,
    SceneModel,
    PromptModel,
)
from Schema.gateway_models import (
    GatewayEnvModel,
    GatewayAppModel,
    GatewayChannelModel,
)

__all__ = [
    # db models
    "FileModel",
    "MemoryModel",
    "SessionModel",
    "ChatLogModel",
    "FileTypeModel",
    # config models
    "ModelConnectionModel",
    "ModelLevelModel",
    "RoleModel",
    "SubAgentModel",
    "SkillModel",
    "ToolModel",
    "FileProcessingModel",
    "SceneModel",
    "PromptModel",
    # gateway models
    "GatewayEnvModel",
    "GatewayAppModel",
    "GatewayChannelModel",
]
