"""Agent路由配置 - 从配置表读，硬编码兜底"""

from dataBase.ConfigService import SubAgentService
from logger import logger

#硬编码兜底
_FALLBACK_REGISTRY = {
    "quotation": "报价计算员：读取报价单并计算报价",
    "reviewer": "保函审核员：根据规则审核保函文本是否符合要求",
}


def _load_from_db():
    try:
        service = SubAgentService()
        agents = service.get_all()
        if agents:
            return {a["name"]: (a.get("description") or "") for a in agents if a.get("name")}
    except:
        pass
    return None


AGENT_REGISTRY = _load_from_db() or _FALLBACK_REGISTRY
ROUTABLE_NEXT = tuple(list(AGENT_REGISTRY.keys()) + ["FINISH"])
