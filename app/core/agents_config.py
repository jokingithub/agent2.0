"""Subagent 配置中心。

后续新增 agent 时，只需在 AGENT_REGISTRY 中新增一项，
并在 builder 中提供对应 node 函数映射即可。
"""

AGENT_REGISTRY = {
    "quotation": "报价计算员：读取报价单并计算报价",
    "reviewer": "保函审核员：根据规则审核保函文本是否符合要求",
}

ROUTABLE_NEXT = tuple(list(AGENT_REGISTRY.keys()) + ["FINISH"])
