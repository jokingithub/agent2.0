# API 与 OCR 环境隔离说明

## 目标

确保 `api.py`（main-app/gateway）与 `ocr-service` 在 Docker 中依赖彻底隔离，避免版本冲突。

## 方案

- API 服务使用：`requirements-api.txt`
- OCR 服务使用：`ocr-service/requirements.txt`
- 两者分别在不同镜像中安装，不共享 Python 依赖层。

## 当前映射

1. `Dockerfile`（主服务镜像）
   - 安装 `requirements-api.txt`
   - 用于：`main-app`、`gateway`

2. `ocr-service/Dockerfile`（OCR 专用镜像）
   - 安装 `ocr-service/requirements.txt`
   - 仅用于：`ocr-service`

## 重建命令（必须）

当你调整任一 requirements 后，执行：

```bash
docker compose build --no-cache main-app gateway ocr-service
docker compose up -d main-app gateway ocr-service
```

> 如果网络无法访问 `docker.io`，当前已默认使用代理基础镜像：
> `m.daocloud.io/docker.io/library/python:3.10-slim`

## 验证

```bash
docker compose exec main-app python -c "import fastapi; print('main-app ok')"
docker compose exec ocr-service python -c "import paddleocr; print('ocr ok')"
```
