```markdown
# CLAUDE.md — Agent 2.0 项目规范

---

## 一、项目概览

Agent 2.0 是一个基于配置驱动的多 Agent 对话系统，核心技术栈包括 FastAPI、PostgreSQL(JSONB)、LangGraph 和 LangChain。系统设计支持多租户（app_id 隔离）、动态 Agent 组合、工具统一管理（基于 MCP 协议）和 HITL（人机交互挂起/恢复）机制。

架构包括：
- **网关服务 (port 9000)**：Bearer Token 鉴权，代理外部请求，工具调用接口限本地 IP。
- **主应用 (port 8000)**：业务接口，LangGraph 工作流，文件上传处理，Agent 运行时。
- **OCR 微服务 (port 8001)**：基于 PaddleOCR 的图像文字识别，独立进程。
- **守护进程**：监控服务健康，自动重启异常服务。
- **MCP 工具服务**：统一工具注册调用，支持远程异步调用。

数据库采用 PostgreSQL + JSONB 文档存储，统一 16 张表存储业务和配置数据，所有业务数据均支持 `app_id` 级隔离。

---

## 二、架构与约束

### 2.1 数据模型约束

- 所有关键业务表 (`files`, `sessions`, `memories`) 都包含 `app_id`，所有业务查询必须以 `app_id` 为过滤条件，确保多租户隔离。
- 配置表（如 `model_connections`, `model_levels`, `roles`, `sub_agents`, `tools`, `scenes` 等）无 `app_id`，全局共享。
- JSONB 存储格式，字段关系通过 ID 数组实现，例如：`roles.sub_agent_ids[]` 指向多个子 Agent。

### 2.2 运行时流程规范

请求进入系统后流程：

1. **网关**：进行 Bearer Token 鉴权，校验 `gateway_apps` 表的 `auth_token`。
2. **代理转发**至主应用，读会话历史和文件列表，载入 LangGraph 运行时上下文。
3. **Supervisor 角色节点**：
   - 优先使用请求中传入 `role_id`，无则从场景默认取第一个角色。
   - 根据角色加载可路由的子 Agent 列表。
   - LLM 决策是直接生成答案 (FINISH) 还是路由到某子 Agent (RUN_AGENT)。
4. **Generic Agent Runner**：执行指定子 Agent。
   - 加载子 Agent 关联的模型、系统提示词、技能和工具。
   - 按需注入会话挂载文件列表。
5. **Generic Tool Runner**：执行工具调用。
   - 工具返回以 `__HITL__` 开头的 JSON 标记，系统自动进入 HITL 挂起状态。
   - 否则继续轮询 Agent / Tool 执行。
6. **SuspendHandler**：将 HITL 挂起信息写入会话，结束当前执行。
7. **异步保存聊天日志**，包含请求、回复、token 消耗和详细计时。

### 2.3 工具系统规范

- 支持三种工具类型：
  - `local`：本地 Python 可调用函数或 LangChain BaseTool，动态加载路径格式为 `module.path:callable`。
  - `mcp`：远程 MCP 服务，定义明确的参数字典及调用名称。
  - `http`：HTTP 接口调用（当前无真实实现，仅为占位）。
- 工具的可见性通过配置字段控制：
  - **enabled** 必须为 true。
  - **expose_to_agent** 为 true 时才暴露给 Agent。
  - 如配置 `allowed_sub_agent_ids`，限制仅部分子 Agent 可见。
- MCP 工具必须在 `config.arg_names` 中以字典形式明确参数类型、是否必填、默认值及描述。
- 工具调用通过网关的 `/gateway/tool/invoke` 代理，本地 IP 限制保护。

### 2.4 配置驱动原则

- 配置表优先，如无配置则依次使用环境变量和硬编码兜底。
- 运行时所有模型、Agent、工具的加载均基于配置表，无需改动代码。
- 配置失败只记录日志，不抛出异常，保障业务持续可用。

### 2.5 会话管理职责分离

| 表名       | 职责                                     |
|------------|------------------------------------------|
| sessions   | 元数据、文件挂载列表、HITL 挂起状态       |
| memories   | 对话历史消息（含角色、模型和 Agent 信息）|
| chat_logs  | 审计日志—请求与回复、token 消耗、执行时间 |

- API 层必须在聊天接口开始时调用 `ensure_session`，结束时调用 `touch_session` 保障活跃时间更新。
- 删除会话时，必须连带删除对应记忆（memories）

### 2.6 文件处理流水线

- 上传文件 → `extract_content`（OCR/PDF文本/图片）→ `file_classfly`（读取 `file_processing` 表确定类型）→ `element_extraction`（按类型抽取字段）
- 抽取使用配置表控制的字段列表和自定义 prompt，支持模糊匹配，采用通用 JSON 解析，避免结构化输出限制。
- 文件存储路径支持临时目录和持久化目录（默认 `/tmp`，可通过 `FILE_STORAGE_ROOT` 配置持久化路径）。
- 文件信息存入 `files` 表，附带完整内容和元数据。

---

## 三、开发规范

### 3.1 增加新的子 Agent

步骤：

1. 在 `sub_agents` 表新增记录（配置 `name`, `system_prompt`, `model_id`, `skill_ids`, `tool_ids`）。
2. 在 `roles` 表的对应角色 `sub_agent_ids` 中关联该子 Agent ID。
3. 确保 `model_id` 指向正确模型分级记录，所有工具与技能已配置且启用。
4. 无需改代码，系统自动加载生效。
5. 编写清晰的系统提示词，包含角色背景和目标。

### 3.2 增加新工具

步骤：

1. 在 `tools` 表新增工具记录。
2. 对于 `local` 类型，配置准确的 Python 入口路径; 对 `mcp` 类型，确保远程 MCP 服务已注册工具和参数。
3. 配置 `enabled` 和 `expose_to_agent` 字段控制可见性。
4. 在对应的 `skills` 或 `sub_agents` 关联此工具。
5. 运行时自动加载。

### 3.3 场景与角色配置

步骤：

1. 创建或更新 `roles` 表，定义多个角色。
2. 创建 `scenes` 表，设置 `available_role_ids` 支持多角色。
3. 前端调用 `/config/scenes/{scene_code}/roles` 获取可选角色列表，传递给聊天接口中的 `role_id` 字段。
4. Supervisor 根据 `role_id` 加载对应角色配置执行。

### 3.4 代码规范

- 命名：Service 类后缀 `Service`；节点函数名以 `_node` 结尾；私有函数前缀 `_`。
- 模块导入顺序：标准库 → 第三方 → 项目内部。
- 日志级别：`info` 常规流程，`warning` 降级/警告，`error` 异常。
- 异常捕获应记录日志，但不抛出影响系统稳定。
- 禁止在 `app/skills/` 添加本地工具（已废弃，全部走 MCP）；禁止硬编码 Agent，全部走配置表。

---

## 四、模块依赖及影响范围

```
基础设施
├── config.py → logger.py
├── dataBase/Schema.py → dataBase/CRUD.py → dataBase/database.py
├── app/core/state.py → app/core/llm.py

数据库层
├── dataBase/Service.py
├── dataBase/ConfigService.py

LLM 层
├── app/core/llm.py → 数据库配置服务

网关层
├── gateway/main.py → router.py → auth.py + store.py

微服务
├── ocr-service
├── mcp-service

业务层
├── app/api.py → app/graph/builder.py
├── app/graph/builder.py → app/agents/* + app/tools/factory.py
├── app/agents/supervisor.py
├── app/agents/generic.py
├── app/agents/generic_runner.py
├── app/tools/factory.py

文件处理
├── fileUpload/fileUpload.py → extract_content → file_classfly → element_extraction
```

修改某模块前请了解其上下游关系，避免影响链式故障。

---

## 五、配置表速查

| 表名             | 关键字段                       | 描述                                         |
|------------------|-------------------------------|----------------------------------------------|
| model_connections | protocol/base_url/api_key/models | 模型连接配置                                   |
| model_levels      | name/level/connection_id/model | 模型分级                                     |
| roles            | name/system_prompt/main_model_id/sub_agent_ids | 角色配置                                     |
| sub_agents       | name/system_prompt/model_id/skill_ids/tool_ids | 子 Agent配置                                  |
| skills           | name/description/tool_ids      | 技能定义                                     |
| tools            | name/type/category/url/method/config/enabled | 工具配置                                     |
| file_processing  | file_type/fields/prompt        | 文件抽取字段配置                             |
| scenes           | scene_code/available_role_ids  | 场景配置（支持多角色）                       |
| gateway_apps     | app_id/auth_token/available_scenes | 访问控制配置                                 |
| gateway_env      | port/whitelist                 | 网关启动配置                                 |
| chat_logs        | app_id/session_id/scene_id/token/timing | 会话日志                                     |
| prompts          | name/type/content/variables/enabled | 自定义提示词库                               |

---

## 六、运行与测试说明

**启动服务：**

```bash
# 安装依赖
pip install -r requirements.txt

# 启动主程序
uvicorn app.api:app --host 0.0.0.0 --port 8000

# 启动网关
uvicorn gateway.main:app --host 0.0.0.0 --port 9000

# 启动 OCR 服务（需激活 ocr-service 环境后）
python ocr-service/main.py

# 或使用 Docker Compose 启动全部服务
docker-compose up
```

**执行测试：**

```bash
python test_config.py    # 配置接口测试
python test_extract.py   # 文件处理测试
python test_llm.py       # Agent 工作流测试
```

---

## 七、开发及调试建议

- 在开发 Agent 或工具后，务必执行全部测试用例。
- 使用 `/mcp/debug/list` 和 `/mcp/debug/call` 接口调试 MCP 工具调用。
- 注意保持数据表配置与代码同步，避免出现加载异常。
- HITL 挂起状态恢复时必须包含 `scene_id` 和 `selected_role_id`，避免角色和 Agent 泄露。
- 前端通过角色选择器传入 `role_id`，必须与配置表保持一致。

---

## 八、常见问题与解决方案

**Q：Agent 配置改了没生效？**
A：Agent 运行时完全依赖配置表，重启服务或重新加载 Graph 后生效，代码无须改动。

**Q：工具调用失败或找不到？**
A：检查工具 `enabled`，`expose_to_agent` 条件，以及是否正确关联到子 Agent 和技能。MCP 服务需正常运行。

**Q：HITL 恢复后子 Agent 列表变动？**
A：确保恢复上下文的 `scene_id` 与 `selected_role_id` 准确，避免错误加载默认角色和子 Agent。

**Q：文件上传识别出错？**
A：确认 `file_processing` 表配置正确，字段名与前端保持一致，必要时调整分类和抽取提示词。

---

此规范旨在让团队成员和自动化工具（如 AI）能够快速上手、稳定开发和高效维护 Agent 2.0 系统。
```