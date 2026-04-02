from core.decorators import register_tool
from core.utils import fetch_external_api
import os


@register_tool(category="crm", description="从内部 CRM 系统获取客户画像。")
async def get_customer_info(user_id: str) -> str:
    """调用内部微服务获取数据。"""
    service_url = "http://internal-crm-service:8080/v1/user/detail"
    
    result = await fetch_external_api(
        url=service_url,
        method="POST",
        json_data={"uid": user_id},
        headers={"Authorization": "Bearer internal-token"}
    )
    return str(result)