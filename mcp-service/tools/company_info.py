from core.decorators import register_tool
from core.utils import fetch_external_api
import os
import asyncio

@register_tool(category="company_info", description="获取公司信息")
async def company_info(name: str) -> str:
    """调用公司爬虫数据。"""
    server_location = "http://120.25.254.115:19000"
    
    # 定义三个协程任务，但先不 await 它们
    tasks = [
        fetch_external_api(url=f"{server_location}/company/get", method="POST", json_data={"name": name}),
        fetch_external_api(url=f"{server_location}/certificate/buildCertificateCheck", method="POST", json_data={"name": name}),
        fetch_external_api(url=f"{server_location}/certificate/certificateCheck", method="POST", json_data={"name": name})
    ]
    
    # 使用 asyncio.gather 并发运行
    # 这会同时发出三个请求
    company_res, zizhi_res, qiye_res = await asyncio.gather(*tasks)
    
    # 组合结果
    result = {
        name: company_res.get("data"), 
        "资质信息": zizhi_res.get("data"), 
        "企业证书": qiye_res.get("data")
    }
    
    return str(result)