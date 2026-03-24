# Daemon 使用说明

## 功能

`supervisor.py` 是一个轻量守护进程：

- 自动 `docker compose up -d` 启动服务
- 定时健康检查：
  - `gateway` -> `http://127.0.0.1:9000/gateway/health`
  - `main-app` -> `http://127.0.0.1:8000/health`
  - `ocr-service` -> `http://127.0.0.1:8001/health`
- 连续2次失败会自动重启对应容器

## 启动

在项目根目录执行：

```bash
python daemon/supervisor.py
```

## 停止

按 `Ctrl + C` 即可优雅停止。
