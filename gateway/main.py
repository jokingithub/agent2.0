# -*- coding: utf-8 -*-
from fastapi import FastAPI
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
app.include_router(gateway_router)
app.include_router(protected_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AI2.0 Gateway is running"}
