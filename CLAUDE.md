# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Project

**Main app (FastAPI on port 8000):**
```bash
pip install -r requirements.txt
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

**Gateway (FastAPI on port 9000):**
```bash
uvicorn gateway.main:app --host 0.0.0.0 --port 9000
```

**OCR microservice (port 8001) — requires separate conda env:**
```bash
cd ocr-service
conda create -n ocr-service python=3.10
conda activate ocr-service
pip install -r requirements.txt
python main.py
```

**Docker (all services + daemon supervisor):**
```bash
docker-compose up
```

**Daemon supervisor (standalone, manages docker services):**
```bash
python daemon/supervisor.py
```

**Run tests:**
```bash
python test_extract.py   # file extraction pipeline
python test_llm.py       # LangGraph agent workflow
python test_config.py    # config CRUD (101 tests)
```

**Environment:** Copy `.env.example` to `.env` and fill in `OPENAI_API_BASE_URL`, `OPENAI_API_KEY`, `PG_URI`, and optional Langfuse keys.

## Project Structure

```
agent2.0/
├── app/                # 主应用 (port 8000)
│   ├── api.py                    # FastAPI 入口（/upload, /chat, /chat/stream, /health）
│   │                             # 含 UsageCollector 回调（token + 三段耗时收集）
│   ├── config_api.py             # 配置管理API（/config/*）
│   ├── Schema.py                 # API 请求/响应模型（ChatRequest 含 app_id/scene_id）
│   ├── core/
│   │   ├── llm.py                # LLM 模型管理（get_model）— 配置驱动 + 硬编码兜底
│   │   ├── state.py              # LangGraph AgentState 定义
│   │   └── agents_config.py      # Agent 路由配置表
│   ├── agents/
│   │   ├── supervisor.py         # Supervisor Agent（路由分发）— 配置驱动
│   │   ├── generic.py            # 通用Agent工厂（从配置表动态创建）
│   │   ├── quotation.py          # 报价 Agent
│   │   └── reviewer.py           # 审核 Agent
│   ├── graph/
│   │   └── builder.py            # LangGraph 工作流构建（当前静态硬编码）
│   ├── skills/                   # 技能目录（skill.md + 实现）
│   │   ├── calculate_skill/      # 计算技能
│   │   └── readFile_skill/       # 读文件技能
│   └── tools/
│       └── factory.py            # 技能自动发现 & Tool 工厂
├── gateway/                # 网关服务 (port 9000)
│   ├── main.py                   # FastAPI 入口
│   ├── auth.py                   # Bearer Token 鉴权（从 gateway_apps 表校验）
│   ├── router.py                 # 代理转发（upload/chat/chat-stream → 8000）+ 工具调用
│   ├── store.py                  # 动态读后端地址 / 校验token / 解析工具配置
│   └── schemas.py                # ToolInvokeRequest
├── daemon/                 # 守护进程
│   └── supervisor.py             # 周期健康检查（15s），连续2次失败自动 docker compose restart
├── dataBase/                     # 数据库层（PostgreSQL + JSONB）
│   ├── database.py               # PG 连接 & 建表（16张）+ JSONB 索引（含 app_id）
│   ├── CRUD.py                   # 通用 JSONB 文档 CRUD（支持 $in、排序、分页）
│   ├── Schema.py                 # Pydantic 数据模型（业务含app_id + 配置共12个Model）
│   ├── Service.py                # 业务 Service（File, Session, Memory）— app_id 隔离
│   └── ConfigService.py          # 配置Service（12张配置表，ChatLogService含字段白名单）
├── fileUpload/                   # 文件上传处理
│   ├── fileUpload.py             # 上传入口（支持多类型分别抽取，含app_id透传）
│   ├── extract_content.py        # 内容提取（DOCX/PDF/图片）
│   ├── file_classfly.py          # 文件分类（优先读 file_processing 表）
│   ├── element_extraction.py     # 要素抽取（配置驱动，从 file_processing 表读）
│   └── Schema.py                 # Letter_Of_Guarantee_Format（历史保留，不再被引用）
├── ocr-service/                  # OCR 微服务（独立进程，port 8001）
│   ├── main.py                   # FastAPI 入口
│   └── OCR/
│       ├── OCR.py                # OCR 逻辑
│       └── paddle_OCR.py         # PaddleOCR 封装
├── prompt/
│   └── file_prompt.py            # 文件处理提示词（历史保留，不再被引用）
├── config.py                     # 环境变量加载
├── logger.py                     # 日志配置
├── docker-compose.yml
├── requirements.txt
├── test_extract.py               # 文件提取测试
├── test_llm.py                   # Agent 工作流测试
└── test_config.py                # 配置 CRUD 测试（101个全过）
```

## Architecture

This is a multi-agent document processing system built on LangGraph + FastAPI.

### Service Architecture

```
External requests → Gateway(:9000) → Bearer Token auth → Proxy → Main App(:8000)
                                                                      ↓
Internal tool calls ← /gateway/tool/invoke (local IP only)      OCR Service(:8001)

Daemon supervisor → periodic health check (15s) → auto docker compose restart on failure
```

Three independent services:
- **Gateway** (port 9000): `gateway/main.py` — auth + proxy + tool invocation
- **Main App** (port 8000): `app/api.py` — core business logic
- **OCR Service** (port 8001): `ocr-service/main.py` — PaddleOCR

### Database

**PostgreSQL with JSONB** — all tables use a unified document-store pattern:
- Each table has `id (VARCHAR PK)` + `data (JSONB)`
- Queries use JSONB operators (`data->>'field'`)

**Connection:** `PG_URI` env var → `postgresql://agent:agent123@localhost:5432/agent`

**Tables (16 total):**
- Business: `files`, `sessions`, `memories`, `config` — all with `app_id` isolation
- System config: `model_connections`, `model_levels`, `gateway_env`, `gateway_apps`, `gateway_channels`, `tools`, `chat_logs`
- Business config: `roles`, `sub_agents`, `skills`, `file_processing`, `scenes`

### Request Flow

1. External requests go through **Gateway** (port 9000) with Bearer Token auth, then proxy to Main App (port 8000).
2. Files are uploaded via `POST /upload` → `fileUpload/fileUpload.py` extracts content (DOCX via mammoth, PDF/images via OCR microservice), deduplicates by MD5, stores in PostgreSQL.
3. Chat requests hit `POST /chat` or `POST /chat/stream` → `app/api.py` loads session memory from PostgreSQL and invokes the LangGraph workflow.
4. The **Supervisor** (`app/agents/supervisor.py`) routes to either a specialized agent or answers directly for simple questions.
5. Specialized agents (**Quotation**, **Reviewer**) use LangChain tools loaded dynamically from skill definitions.
6. Chat logs are saved asynchronously with token usage + three-stage timing collected via `UsageCollector` callback.

### Gateway (`gateway/`)

The gateway is a separate FastAPI service that handles:

- **Auth**: Bearer Token validation against `gateway_apps` table (`gateway/auth.py`)
- **Proxy**: Forwards `/gateway/upload`, `/gateway/chat`, `/gateway/chat/stream` to Main App
- **Tool invocation**: `POST /gateway/tool/invoke` — local IP only, resolves tool config from `tools` table, builds target URL/method/headers, forwards request
- **Config store**: `gateway/store.py` reads backend URL from `gateway_env` table (whitelist → env var → default), validates tokens against `gateway_apps`

Protected routes (upload/chat/chat-stream) require Bearer Token. Public routes (health/backend/tool-invoke) do not.

**Note:** `available_scenes` is stored as `List[Dict]` (with scene_code + features) but scene-level permission checking is not yet implemented in auth.py.

### Daemon Supervisor (`daemon/supervisor.py`)

Simple process that:
1. Starts all services via `docker compose up -d`
2. Checks health endpoints every 15 seconds
3. Restarts containers after 2 consecutive health check failures
4. Handles SIGINT/SIGTERM gracefully

### File Processing Pipeline (Config-Driven)

```
Upload file (with app_id)
  → extract_content.py (OCR/text extraction, unchanged)
  → file_classfly.py (AI classification)
      → reads available types from file_processing table (fallback: config table → hardcoded defaults)
      → returns list of types, e.g. ["保函"]
  → element_extraction.py (element extraction, per type)
      → for each classified type:
          → query file_processing table by file_type (exact match, then fuzzy match)
          → if custom prompt exists: use it directly
          → if not: build prompt from _DEFAULT_PROMPT_TEMPLATE + fields list
          → LLM returns JSON → _parse_json_response() extracts dict
      → merge all results into single dict
  → store in files table as main_info (Dict[str, Any]) with app_id
```

**Key design decisions:**
- `fields` use English keys (e.g. `beneficiary`, `guarantee_amount`) for consistency with legacy data
- Custom `prompt` field maps English keys to Chinese descriptions (e.g. `- beneficiary: 受益人`)
- No longer uses Pydantic `with_structured_output` — replaced with generic JSON parsing to support arbitrary file types
- `fileUpload/Schema.py` (Letter_Of_Guarantee_Format) and `prompt/file_prompt.py` are preserved but no longer referenced

**To add a new file type:** Insert a record into `file_processing` table via `/config/file-processing` API. No code changes needed.

### Configuration-Driven Runtime

The system reads runtime configuration from PostgreSQL config tables instead of hardcoded values:

**Model resolution chain:**
```
get_model("high")
  → query model_levels table (match by name)
  → get connection_id + model name
  → query model_connections table (get base_url + api_key)
  → build ChatOpenAI instance
  → fallback to hardcoded .env values if config tables are empty
```

**Agent creation chain:**
```
Agent node invoked
  → query sub_agents table (match by name)
  → read system_prompt, model_id, skill_ids, tool_ids
  → model_id → model_levels → model_connections → ChatOpenAI
  → tool_ids → tools table → Tool objects (MCP/HTTP, currently placeholder)
  → skill_ids → skills table → tool_ids → more Tool objects
  → merge with local skills from app/skills/ directory
  → build agent chain
  → fallback to hardcoded agent if config not found
```

**Supervisor routing chain:**
```
Request arrives
  → query roles table (find "supervisor" role)
  → read system_prompt + main_model_id
  → query sub_agents table → build available agent list
  → LLM decides routing → next agent or FINISH
  → fallback to hardcoded AGENT_REGISTRY if config tables empty
```

### Chat Logging (`UsageCollector` in `app/api.py`)

Chat logs are collected without external dependencies (no Langfuse required):

**Token collection:** `UsageCollector(BaseCallbackHandler)` — lightweight callback that:
- `on_llm_start()` — records first LLM start time (`first_token_time`)
- `on_llm_end()` — accumulates token usage across all LLM calls (supports multi-agent workflows)

**Three-stage timing:**
- `request_time` — when the request arrives (manual)
- `first_token_time` — when the first LLM starts generating (callback)
- `end_time` — when everything completes (manual)

**Fields saved to `chat_logs` table:**
`app_id, scene_id, session_id, request_content, response_content, request_time, first_token_time, end_time, total_tokens, prompt_tokens, completion_tokens`

**Write strategy:** Async (`asyncio.create_task`), does not block streaming responses. `ChatLogService.save_log_async` applies field whitelist filtering to prevent dirty fields.

### Session Management

Three tables with distinct responsibilities:

| Table | Responsibility |
|-------|---------------|
| `sessions` | Session metadata + file_list + created_at/updated_at/status |
| `memories` | Conversation history (role/content/ts messages array) |
| `chat_logs` | Audit log (request/response + token + timing, append-only) |

**SessionService** orchestrates all three:
- `ensure_session(session_id, app_id)` — idempotent create
- `touch_session(session_id, app_id)` — refresh `updated_at`
- `add_file_to_session(session_id, file_info, app_id)` — save file + mount to session
- `append_chat_message(session_id, role, content, app_id)` — write to memories + ensure session + touch

**API guarantees:** `/chat` and `/chat/stream` call `ensure_session` at start, `touch_session` at end.

### App Isolation

All business tables (`files`, `sessions`, `memories`) include `app_id` field:
- Schema layer: `FileModel`, `SessionModel`, `MemoryModel` all have `app_id: str = ""`
- Index layer: `database.py` creates JSONB indexes on `app_id` for all three tables
- Service layer: All queries filter by `app_id` when provided
- API layer: `/upload` accepts `app_id` as Form parameter; `/chat` reads from `ChatRequest.app_id`

### LangGraph Workflow (`app/graph/builder.py`)

```
START → supervisor → [quotation | reviewer | END]
                ↓
                    tool_node → agent (loop until done)
```

Routing is driven by `AgentState.next` (set by supervisor) and `should_continue` (checks for tool calls).

**Note:** Graph structure is currently static (hardcoded nodes/edges). Will be refactored when n8n workflows are migrated.

### Skill/Tool System (`app/tools/factory.py`)

Two tool sources, merged at runtime:

1. **Local skills** — defined in `skill.md` files inside `app/skills/<name>/` with YAML front matter specifying `name`, `description`, and `entrypoint` (`module.path:function`). Auto-discovered and wrapped as LangChain `Tool` objects.

2. **Config table tools** — loaded from `tools` PostgreSQL table. Supports MCP and HTTP types (currently placeholder implementations). Loaded via `load_tool_from_config(tool_id)` or `load_tools_for_sub_agent(sub_agent_id)`.

Tool invocation from agents goes through `gateway/tool/invoke` endpoint (local IP only), which resolves tool config, builds target URL, and forwards the request.

### Config Management (`app/config_api.py`)

All config CRUD is under `/config/*` prefix. Uses `BaseConfigService` pattern — each config type has:
- Standard CRUD: `GET /`, `GET /{id}`, `POST /`, `PUT /{id}`, `DELETE /{id}`
- Special endpoints for relationships (add/remove sub-agents, skills, tools, roles)
- Special endpoints: gateway env (singleton), token validation, fallback chain, enabled tools

**Gateway apps creation:** Only requires `app_id` + `available_scenes`. The `auth_token` is auto-generated via `secrets.token_urlsafe(32)` and returned in the response.

**Swagger docs:** `register_crud_routes` uses closures to capture `model_class`, so Swagger shows full field schemas for create/update endpoints.

### LLM Models (`app/core/llm.py`)

**Priority: config table → hardcoded fallback.**

Config-driven: reads from `model_connections` + `model_levels` tables.

Two entry points:
- `get_model(tier)` — by tier name ("high"/"medium"/"low"/"test") or by model_level ID
- `get_model_by_level_id(level_id)` — direct lookup by model_level record ID (used by sub_agents)

Hardcoded fallback (used when config tables are empty):
- `"high"` → `google/gemini-3-flash-preview`
- `"medium"` → `google/gemini-2.5-pro-preview`
- `"low"` → `google/gemini-1.5-pro-preview`
- `"test"` → `qwen3.5-35b-a3b`

### OCR Microservice (`ocr-service/`)

Standalone FastAPI service using PaddleOCR. Decoupled from the main app via HTTP. Requires its own conda environment due to PaddleOCR's heavy dependencies.

## Module Dependency Map

> 新增模块时，在此补充它的上下游关系，无需重新读取整个项目。

### 基础设施（无项目内依赖）
- `config.py` — 环境变量加载（含 PG_URI）
- `logger.py` → `config.Config`
- `dataBase/Schema.py` — Pydantic 数据模型（业务模型含app_id + 配置模型共12个）
- `dataBase/CRUD.py` — PostgreSQL JSONB 通用增删改查（支持 $in、排序、分页）
- `app/core/state.py` — LangGraph AgentState 定义
- `app/core/agents_config.py` — Agent 路由配置表

### 数据库层
- `dataBase/database.py` → `config`, `logger` — PostgreSQL 连接，自动建表（16张）+ JSONB 索引（含 app_id 索引）
- `dataBase/Service.py` → `database.Database`, `CRUD.CRUD`, `dataBase/Schema`
  - 提供：`FileService`, `SessionService`, `MemoryService`, `FileTypeService`
  - 所有业务 Service 支持 app_id 隔离
- `dataBase/ConfigService.py` → `database.Database`, `CRUD.CRUD`, `dataBase/Schema`
  - 提供：`ModelConnectionService`, `ModelLevelService`, `GatewayEnvService`, `GatewayAppService`, `GatewayChannelService`, `ToolService`, `ChatLogService`, `RoleService`, `SubAgentService`, `SkillService`, `FileProcessingService`, `SceneService`
  - `ChatLogService` 含字段白名单过滤，防止脏字段写入

### LLM 核心
- `app/core/llm.py` → `config`, `logger`, `dataBase/ConfigService.ModelLevelService`, `dataBase/ConfigService.ModelConnectionService`
  - 提供：`get_model(tier)` — 优先配置表，兜底硬编码
  - 提供：`get_model_by_level_id(id)` — 子Agent用，按ID直接查

### 网关层
- `gateway/main.py` → `gateway/router` — FastAPI 入口（port 9000）
- `gateway/auth.py` → `gateway/store` — Bearer Token 鉴权
- `gateway/router.py` → `gateway/auth`, `gateway/store`, `gateway/schemas`, `app/Schema`
  - 暴露：`GET /gateway/health`（公开）
  - 暴露：`GET /gateway/backend`（公开）
  - 暴露：`POST /gateway/tool/invoke`（公开，仅本地IP）
  - 暴露：`POST /gateway/upload`（需Token）
  - 暴露：`POST /gateway/chat`（需Token）
  - 暴露：`POST /gateway/chat/stream`（需Token）
- `gateway/store.py` → `dataBase/ConfigService.GatewayEnvService`, `dataBase/ConfigService.GatewayAppService`, `dataBase/ConfigService.ToolService`, `logger`
  - 提供：`get_backend_base_url()` — 从 gateway_env 表 / 环境变量 / 默认值
  - 提供：`validate_token(token)` — 遍历 gateway_apps 匹配 auth_token
  - 提供：`get_tool(tool_id)` — 按 _id 或 name 查工具
  - 提供：`build_tool_target(tool_doc, backend)` — 解析工具目标地址/方法/headers
- `gateway/schemas.py` — `ToolInvokeRequest`（tool_id + params）

### 守护进程
- `daemon/supervisor.py` — 独立运行，无项目内 import
  - 依赖：`httpx`（健康检查）、`subprocess`（docker compose 命令）
  - 检查：gateway(:9000), main-app(:8000), ocr-service(:8001)

### 文件上传流水线（配置驱动）
- `fileUpload/extract_content.py` → `logger`
  - 调用：OCR microservice HTTP `http://127.0.0.1:8001/ocr/process`
- `fileUpload/file_classfly.py` → `app/core/llm`, `logger`, `dataBase/Service.FileTypeService`, `dataBase/ConfigService.FileProcessingService`
  - 分类类型优先从 file_processing 表读，兜底 config 表 → 硬编码默认值
- `fileUpload/element_extraction.py` → `app/core/llm`, `dataBase/ConfigService.FileProcessingService`, `logger`
  - 从 file_processing 表读 fields + prompt，支持精确/模糊匹配
  - 通用 JSON 解析（不再依赖 Pydantic structured output）
  - 不再依赖：`fileUpload/Schema.py`, `prompt/file_prompt.py`
- `fileUpload/fileUpload.py` → `dataBase/Schema`, `dataBase/Service`, `file_classfly`, `extract_content`, `element_extraction`, `logger`
  - 对每个分类类型分别调用 element_extraction，合并结果
  - 含 app_id 透传（3处）
  - ← 被调用：`app/api.py` (POST /upload)
- `fileUpload/Schema.py` — Letter_Of_Guarantee_Format（历史保留，无引用）
- `prompt/file_prompt.py` — 硬编码提示词（历史保留，无引用）

### 技能/工具层
- `app/skills/calculate_skill/` — 纯数学计算，无项目依赖
- `app/skills/readFile_skill/` → `dataBase/Service.FileService`
- `app/tools/factory.py` → `logger`, `dataBase/ConfigService.ToolService`, `dataBase/ConfigService.SkillService`, `dataBase/ConfigService.SubAgentService`
  - 提供：`load_skill_as_tool(dir)` — 本地skill加载（不变）
  - 提供：`load_tool_from_config(id)` — 从tools表加载单个工具
  - 提供：`load_tools_from_config(ids)` — 批量从tools表加载
  - 提供：`load_tools_for_sub_agent(id)` — 加载子Agent全部工具（直接+技能间接）
  - ← 被调用：`app/agents/generic.py`, `app/agents/quotation.py`, `app/agents/reviewer.py`, `app/graph/builder.py`

### Agent 层
- `app/agents/generic.py` → `app/core/llm`, `app/tools/factory`, `dataBase/ConfigService.SubAgentService`, `logger`
  - 提供：`create_agent_from_config(sub_agent_id)` — 从配置表动态创建Agent
  - 提供：`generic_agent_node(sub_agent_id)` — 返回graph node函数
- `app/agents/supervisor.py` → `app/core/llm`, `app/core/agents_config`, `dataBase/ConfigService.RoleService`, `dataBase/ConfigService.SubAgentService`, `logger`
  - 优先从roles表读提示词+模型，从sub_agents表读可路由Agent
  - 兜底用硬编码 AGENT_REGISTRY
- `app/agents/quotation.py` → `app/core/llm`, `app/tools/factory`, `app/agents/generic`, `dataBase/ConfigService.SubAgentService`, `logger`
  - 优先从配置表创建，兜底硬编码
- `app/agents/reviewer.py` → `app/core/llm`, `app/tools/factory`, `app/agents/generic`, `dataBase/ConfigService.SubAgentService`, `logger`
  - 优先从配置表创建，兜底硬编码

### 图/工作流
- `app/graph/builder.py` → `app/core/state`, `app/core/agents_config`, 所有 agents, `app/tools/factory`
  - **注意：** 当前graph结构仍为静态硬编码，待n8n工作流迁移后重构

### API 入口
- `app/api.py` → `app/graph/builder`, `app/Schema`, `fileUpload/fileUpload`, `logger`, `app/config_api`, `dataBase/ConfigService.ChatLogService`, `dataBase/Service.SessionService`
  - 暴露：`POST /upload`（含 app_id Form 参数）, `POST /chat`, `POST /chat/stream`, `GET /health`
  - 含 `UsageCollector(BaseCallbackHandler)` — 轻量回调收集 token + 首次输出时间
  - 会话日志异步写入（app_id, scene_id, session_id, request/response, token消耗, 三段耗时）
  - 会话管理：开始时 `ensure_session`，结束时 `touch_session`
- `app/config_api.py` → `dataBase/ConfigService`, `dataBase/Schema`
  - 暴露：`/config/*` 所有配置管理接口
  - Swagger 用闭包捕获 model_class，显示完整字段

### OCR 微服务（独立进程）
- `ocr-service/OCR/paddle_OCR.py` — PaddleOCR 封装，无项目依赖
- `ocr-service/OCR/OCR.py` → `OCR/paddle_OCR`
- `ocr-service/main.py` → `OCR/OCR`
  - 暴露：`POST /ocr/process`（port 8001）

## Config Tables Reference

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `model_connections` | 模型连接 | protocol, base_url, api_key, models |
| `model_levels` | 模型分级 | name, level, connection_id, model |
| `gateway_env` | 网关环境（单例） | port, whitelist |
| `gateway_apps` | 外部调用配置 | app_name, app_id (auto-generated), auth_token (auto-generated), available_scenes (List[Dict]), description |
| `gateway_channels` | 渠道配置 | channel, enabled, webhook_url |
| `tools` | 工具 | name, type(mcp/http), category, url, method, config(path/headers/timeout), enabled |
| `chat_logs` | 会话日志 | app_id, scene_id, session_id, request/response_content, request_time, first_token_time, end_time, total/prompt/completion_tokens |
| `roles` | 角色/人设 | name, system_prompt, main_model_id, sub_agent_ids |
| `sub_agents` | 子Agent | name, system_prompt, model_id, skill_ids, tool_ids |
| `skills` | 技能 | name, description, tool_ids |
| `file_processing` | 文件处理 | file_type, fields (English keys), prompt (optional custom) |
| `scenes` | 场景配置 | scene_code, available_role_ids, route_key |

## Relationships (stored as ID arrays in JSONB)

```
Scene → Role → SubAgent → Skill → Tool
              ↓           ↓
         ModelLevel → ModelConnection
```

- Role → SubAgent: `roles.sub_agent_ids[]`
- SubAgent → Skill: `sub_agents.skill_ids[]`
- SubAgent → Tool: `sub_agents.tool_ids[]`
- Skill → Tool: `skills.tool_ids[]`
- Scene → Role: `scenes.available_role_ids[]`
- ModelLevel → ModelConnection: `model_levels.connection_id`
- Role → ModelLevel: `roles.main_model_id`, `roles.fallback_model_id`
- SubAgent → ModelLevel: `sub_agents.model_id`

## Test Data Setup

Insert config data in this order (respecting foreign key references):

```bash
# 1. model_connections → get <connection_id>
# 2. model_levels (reference connection_id) → get <model_level_id>
# 3. sub_agents (reference model_level_id) → get <quotation_id>, <reviewer_id>
# 4. roles (reference model_level_id + sub_agent_ids)
# 5. file_processing (for file upload pipeline)
# 6. scenes (reference role_ids)
# 7. gateway_apps (for external access, app_id + auth_token both auto-generated, only pass app_name + available_scenes + description)
```

Example file_processing config (保函):
```json
{
    "file_type": "保函",
    "fields": ["beneficiary", "the_guaranteed", "types_of_guarantee", "number", "project_name", "guarantee_amount", "bank"],
    "prompt": "# Role\n你是专业的数据抽取专家...\n# Extraction Schema\n- beneficiary: 受益人\n- the_guaranteed: 被保证人\n- types_of_guarantee: 保函品种\n- number: 保函编号\n- project_name: 项目名称\n- guarantee_amount: 担保金额，单位：元\n- bank: 开函银行\n..."
}
```

Use `/config/*` POST endpoints or curl commands. See test_config.py for examples.

## Fallback Strategy

All config-driven modules have hardcoded fallbacks:

| Module | Config source | Fallback |
|--------|--------------|----------|
| `llm.py` | model_connections + model_levels | .env OPENAI_API_BASE_URL + hardcoded model map |
| `agents_config.py` | sub_agents table | _FALLBACK_REGISTRY dict |
| `supervisor.py` | roles + sub_agents tables | hardcoded prompt + AGENT_REGISTRY |
| `quotation.py` | sub_agents table | hardcoded prompt + local skills |
| `reviewer.py` | sub_agents table | hardcoded prompt + local skills |
| `factory.py` | tools table | MCP/HTTP placeholder functions |
| `element_extraction.py` | file_processing table | returns empty dict (no error) |
| `file_classfly.py` | file_processing table → config table | hardcoded default types list |
| `gateway/store.py` | gateway_env table | env var BACKEND_BASE_URL → default 127.0.0.1:8000 |

## Dead Code (preserved, not referenced)

These files are kept for historical reference but are no longer imported anywhere:

- `fileUpload/Schema.py` — `Letter_Of_Guarantee_Format` Pydantic model (replaced by generic Dict[str, Any])
- `prompt/file_prompt.py` — hardcoded extraction prompts (replaced by file_processing table config)