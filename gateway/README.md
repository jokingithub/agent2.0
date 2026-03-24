# Gateway 独立服务

## 启动

### 本地启动
```bash
uvicorn gateway.main:app --host 0.0.0.0 --port 9000 --reload
```

### Docker Compose 启动
```bash
docker compose up -d gateway
```

## 核心能力

1. 从数据库动态读取后端地址：
   - 集合：`gateway_env`
   - 优先读取 `whitelist[0]`（完整URL）
   - 否则使用 `port` 拼接 `http://127.0.0.1:{port}`

2. 动态工具调用：
   - 接口：`POST /gateway/tool/invoke`
   - 参数：`tool_id`, `params`
   - 从 `tools` 表动态读取工具配置并转发
   - 仅允许本地IP访问（`127.0.0.1` / `::1`）
   - 不需要 token 鉴权

3. 上传接口鉴权转发：
   - 接口：`POST /gateway/upload`
   - 转发到后端 `/upload`
   - 鉴权：通过路由装饰器统一校验 `Authorization: Bearer <token>`，与 `gateway_apps.auth_token` 比对

4. 问答接口鉴权转发：
   - 接口：`POST /gateway/chat`
   - 接口：`POST /gateway/chat/stream`
   - 转发到后端 `/chat` 与 `/chat/stream`
   - 同样走统一装饰器鉴权

5. App 注册与 token 生成：
   - 接口：`POST /app/register`（在主服务 `app/api.py`）
   - 请求体只需要 `app_id` 和 `available_scenes`
   - `auth_token` 由服务端自动生成并返回
   - 若 `app_id` 已存在，会自动重置新 token

## 工具配置约定（tools.data）

- `url`：完整URL或路径（如 `/some/tool`）
- `enabled`：是否启用（true/false）
- `config`（可选）
  - `path`: 路径（优先于url）
  - `method`: HTTP方法，默认POST
  - `extra_headers`: 透传头
  - `auth_required`: 是否要求调用方带token
  - `timeout_sec`: 超时秒数，默认30

## 鉴权策略

- 对外公开接口：
   - `GET /gateway/health`
   - `GET /gateway/backend`
   - `POST /gateway/tool/invoke`（仅本地IP允许）
- 受保护接口（统一装饰器鉴权）：
   - `POST /gateway/upload`
   - `POST /gateway/chat`
   - `POST /gateway/chat/stream`
