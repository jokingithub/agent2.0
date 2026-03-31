import httpx
from logger import logger

async def fetch_external_api(url, method="GET", params=None, json_data=None, headers=None, timeout=10):
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"🌐 请求外部接口: [{method}] {url}")
            response = await client.request(
                method=method, url=url, params=params, json=json_data, headers=headers, timeout=timeout
            )
            response.raise_for_status()
            return response.json() if "application/json" in response.headers.get("content-type", "") else response.text
        except Exception as e:
            logger.error(f"❌ 网络请求失败: {str(e)}")
            return f"调用失败: {str(e)}"