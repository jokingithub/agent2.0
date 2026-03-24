# -*- coding: utf-8 -*-
from fastapi import FastAPI

from gateway.router import router as gateway_router, protected_router

app = FastAPI(title="AI2.0 Gateway", version="1.0.0")
app.include_router(gateway_router)
app.include_router(protected_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AI2.0 Gateway is running"}
