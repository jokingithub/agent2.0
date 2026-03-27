# -- coding: utf-8 --

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # 1. 导入中间件
from config import Config

from gateway.router import router as gateway_router, protected_router

_docs_url = "/docs" if Config.ENABLE_API_DOCS else None
_redoc_url = "/redoc" if Config.ENABLE_API_DOCS else None
_openapi_url = "/openapi.json" if Config.ENABLE_API_DOCS else None

app = FastAPI(
    title="AI2.0 Gateway",
    version="1.0.0",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

# 2. 定义允许的源（即允许哪些前端域名访问）
# 如果是在开发环境，可以使用 ["*"] 允许所有。在生产环境建议指定具体域名。
origins = [
    "http://localhost",
    "http://localhost:3000",  # 常见的 React/Next.js 端口
    "https://your-frontend-domain.com", 
    "*", # 临时允许所有来源，方便调试
]

# 3. 将中间件添加到 app
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           # 允许跨域的源列表
    allow_credentials=True,          # 允许携带 Cookie
    allow_methods=["*"],             # 允许所有的 HTTP 方法 (GET, POST, OPTIONS, 等)
    allow_headers=["*"],             # 允许所有的请求头
)

app.include_router(gateway_router)
app.include_router(protected_router)

@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AI2.0 Gateway is running"}