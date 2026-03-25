# -*- coding: utf-8 -*-
"""
配置接口CRUD测试（交互式，逐步执行）
运行：python test_config.py

覆盖全部 12 个配置表 + 关联关系 + 特殊接口
"""
import requests
import json
import sys

BASE_URL = "http://localhost:8000/config"

passed = 0
failed = 0
errors = []


def pause(hint=""):
    """等待用户按回车继续"""
    msg = f"\n⏸️  {hint}" if hint else ""
    input(f"{msg}\n👉 按回车继续...")


def test(name, method, url, expected_status, body=None):
    global passed, failed
    try:
        if method == "GET":
            r = requests.get(url)
        elif method == "POST":
            r = requests.post(url, json=body)
        elif method == "PUT":
            r = requests.put(url, json=body)
        elif method == "DELETE":
            r = requests.delete(url)

        if r.status_code == expected_status:
            passed += 1
            print(f"  ✅ {name}")
            if r.text:
                data = r.json()
                print(f"     响应: {json.dumps(data, ensure_ascii=False, indent=2)[:2000]}")
                return data
            return None
        else:
            failed += 1
            errors.append(f"{name}: 期望{expected_status}, 实际{r.status_code}")
            print(f"  ❌ {name} (期望{expected_status}, 实际{r.status_code})")
            print(f"     响应: {r.text[:500]}")
            return None
    except Exception as e:
        failed += 1
        errors.append(f"{name}: 异常 {e}")
        print(f"  ❌ {name} (异常: {e})")
        return None


def cleanup(path, items):
    """批量清理测试数据"""
    for item in items:
        doc_id = item.get("_id") or item.get("id")
        if doc_id:
            requests.delete(f"{BASE_URL}/{path}/{doc_id}")
    print(f"  🧹 已清理 {path} 的测试数据")


def cleanup_all(path):
    """清理某个表的全部数据"""
    r = requests.get(f"{BASE_URL}/{path}")
    if r.status_code == 200:
        items = r.json()
        cleanup(path, items)


if __name__ == "__main__":
    print("🚀 配置接口CRUD交互式测试（完整版）")
    print("每一步会暂停，你可以去 Database Client 查看数据变化\n")

    # ============================================================
    # 1. 模型连接
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 1. 模型连接 (model_connections)")
    print(f"{'='*60}")

    pause("准备创建模型连接")

    result = test("创建模型连接-OpenAI", "POST", f"{BASE_URL}/model-connections", 200, {
        "protocol": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-test-key-123",
        "models": ["gpt-4", "gpt-3.5-turbo"],
        "description": "OpenAI官方"
    })
    conn_id = result["id"] if result else None

    result2 = test("创建模型连接-DeepSeek", "POST", f"{BASE_URL}/model-connections", 200, {
        "protocol": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-ds-test-456",
        "models": ["deepseek-chat", "deepseek-coder"],
        "description": "DeepSeek"
    })
    conn_id2 = result2["id"] if result2 else None

    pause("刷新 Database Client，model_connections 表应该有 2 条")

    test("查询所有模型连接", "GET", f"{BASE_URL}/model-connections", 200)

    if conn_id:
        test("查询单个模型连接", "GET", f"{BASE_URL}/model-connections/{conn_id}", 200)

        test("更新模型连接", "PUT", f"{BASE_URL}/model-connections/{conn_id}", 200, {
            "description": "OpenAI官方-已更新",
            "models": ["gpt-4", "gpt-3.5-turbo", "gpt-4o"]
        })

        pause("看看 description 和 models 是否更新了")

        test("验证更新结果", "GET", f"{BASE_URL}/model-connections/{conn_id}", 200)

    test("查询不存在的(应该404)", "GET", f"{BASE_URL}/model-connections/fake-id-999", 404)
    test("删除不存在的(应该404)", "DELETE", f"{BASE_URL}/model-connections/fake-id-999", 404)

    # 暂不清理，后面模型分级要用

    # ============================================================
    # 2. 模型分级
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 2. 模型分级 (model_levels)")
    print(f"{'='*60}")

    pause("准备创建模型分级（关联刚才的模型连接）")

    result = test("创建模型分级-主力", "POST", f"{BASE_URL}/model-levels", 200, {
        "name": "主力模型",
        "level": 1,
        "connection_id": conn_id or "test-conn-id",
        "model": "gpt-4",
        "max_retry": 3,
        "timeout": 30
    })
    level_id1 = result["id"] if result else None

    result = test("创建模型分级-备用", "POST", f"{BASE_URL}/model-levels", 200, {
        "name": "备用模型",
        "level": 2,
        "connection_id": conn_id or "test-conn-id",
        "model": "gpt-3.5-turbo",
        "max_retry": 3,
        "timeout": 20
    })
    level_id2 = result["id"] if result else None

    result = test("创建模型分级-兜底", "POST", f"{BASE_URL}/model-levels", 200, {
        "name": "兜底模型",
        "level": 3,
        "connection_id": conn_id2 or "test-conn-id-2",
        "model": "deepseek-chat",
        "max_retry": 5,
        "timeout": 60
    })
    level_id3 = result["id"] if result else None

    pause("model_levels 表应该有 3 条，level 分别是 1、2、3")

    test("获取模型降级链(按level排序)", "GET", f"{BASE_URL}/model-levels/fallback-chain", 200)

    pause("返回顺序应该是 level 1→2→3（主力→备用→兜底）")

    if level_id1:
        test("更新模型分级", "PUT", f"{BASE_URL}/model-levels/{level_id1}", 200, {
            "name": "主力模型-已更新",
            "max_retry": 5
        })
        test("验证更新", "GET", f"{BASE_URL}/model-levels/{level_id1}", 200)

    # 暂不清理，后面 sub_agent/role 要用

    # ============================================================
    # 3. 工具
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 3. 工具 (tools)")
    print(f"{'='*60}")

    pause("准备创建工具")

    r = test("创建工具-联网搜索(MCP)", "POST", f"{BASE_URL}/tools", 200, {
        "name": "联网搜索",
        "type": "mcp",
        "category": "web_search",
        "url": "https://mcp-server.example.com",
        "method": "POST",
        "enabled": True,
        "description": "MCP联网搜索",
        "config": {
            "tool_name": "web_search",
            "transport": "sse",
            "timeout_sec": 15
        }
    })
    tool_id1 = r["id"] if r else None

    r = test("创建工具-OCR(HTTP)", "POST", f"{BASE_URL}/tools", 200, {
        "name": "OCR识别",
        "type": "http",
        "category": "ocr",
        "url": "http://localhost:8001",
        "method": "POST",
        "enabled": True,
        "description": "图片文字识别",
        "config": {
            "path": "/ocr/process",
            "extra_headers": {},
            "auth_required": False,
            "timeout_sec": 30
        }
    })
    tool_id2 = r["id"] if r else None

    r = test("创建工具-报告workflow(HTTP)", "POST", f"{BASE_URL}/tools", 200, {
        "name": "报告生成",
        "type": "http",
        "category": "workflow",
        "url": "https://n8n.company.com",
        "method": "POST",
        "enabled": True,
        "description": "n8n报告生成工作流",
        "config": {
            "path": "/webhook/report-gen",
            "auth_required": True,
            "timeout_sec": 120
        }
    })
    tool_id3 = r["id"] if r else None

    r = test("创建工具-已禁用", "POST", f"{BASE_URL}/tools", 200, {
        "name": "报价计算",
        "type": "http",
        "category": "api",
        "method": "POST",
        "enabled": False,
        "description": "暂未启用"
    })
    tool_id4 = r["id"] if r else None

    pause("tools 表应该有 4 条，3 条启用 1 条禁用")

    test("查询启用的工具", "GET", f"{BASE_URL}/tools/enabled", 200)
    pause("应该返回 3 条（联网搜索、OCR、报告生成）")

    test("按类型查工具-mcp", "GET", f"{BASE_URL}/tools/type/mcp", 200)
    pause("应该返回 1 条（联网搜索）")

    test("按类型查工具-http", "GET", f"{BASE_URL}/tools/type/http", 200)
    pause("应该返回 3 条（OCR、报告生成、报价计算）")

    if tool_id1:
        test("更新工具-禁用联网搜索", "PUT", f"{BASE_URL}/tools/{tool_id1}", 200, {
            "enabled": False
        })
        test("再查启用工具", "GET", f"{BASE_URL}/tools/enabled", 200)
        pause("应该只剩 2 条了")

        # 恢复启用
        test("恢复启用联网搜索", "PUT", f"{BASE_URL}/tools/{tool_id1}", 200, {
            "enabled": True
        })

    # 暂不清理，后面技能/子Agent要用

    # ============================================================
    # 4. 技能
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 4. 技能 (skills)")
    print(f"{'='*60}")

    pause("准备创建技能")

    r = test("创建技能-搜索技能", "POST", f"{BASE_URL}/skills", 200, {
        "name": "搜索技能",
        "description": "联网搜索并总结信息"
    })
    skill_id1 = r["id"] if r else None

    r = test("创建技能-文件处理技能", "POST", f"{BASE_URL}/skills", 200, {
        "name": "文件处理技能",
        "description": "OCR识别和文件内容提取"
    })
    skill_id2 = r["id"] if r else None

    pause("skills 表应该有 2 条")

    test("查询所有技能", "GET", f"{BASE_URL}/skills", 200)

    if skill_id1:
        test("查询单个技能", "GET", f"{BASE_URL}/skills/{skill_id1}", 200)

        test("更新技能", "PUT", f"{BASE_URL}/skills/{skill_id1}", 200, {
            "description": "联网搜索并总结信息-已更新"
        })
        test("验证更新", "GET", f"{BASE_URL}/skills/{skill_id1}", 200)

    # 技能关联工具
    if skill_id1 and tool_id1:
        print("\n  🔗 技能 ← 工具")
        test("技能添加工具-联网搜索", "POST",
             f"{BASE_URL}/skills/{skill_id1}/tools/{tool_id1}", 200)
        pause("skills 表的 tool_ids 应该包含联网搜索工具ID")
        test("验证技能详情", "GET", f"{BASE_URL}/skills/{skill_id1}", 200)

    if skill_id2 and tool_id2:
        test("技能添加工具-OCR", "POST",
             f"{BASE_URL}/skills/{skill_id2}/tools/{tool_id2}", 200)

    # ============================================================
    # 5. 子Agent
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 5. 子Agent (sub_agents)")
    print(f"{'='*60}")

    pause("准备创建子Agent（关联模型分级）")

    r = test("创建子Agent-搜索Agent", "POST", f"{BASE_URL}/sub-agents", 200, {
        "name": "搜索Agent",
        "description": "负责联网搜索和信息汇总",
        "system_prompt": "你是一个专业的搜索助手，擅长联网搜索并总结关键信息。",
        "model_id": level_id1 or "test-model-level-id"
    })
    agent_id1 = r["id"] if r else None

    r = test("创建子Agent-报价Agent", "POST", f"{BASE_URL}/sub-agents", 200, {
        "name": "报价Agent",
        "description": "负责保函报价计算",
        "system_prompt": "你是一个专业的保函报价专家，根据保函信息计算报价。",
        "model_id": level_id2 or "test-model-level-id"
    })
    agent_id2 = r["id"] if r else None

    r = test("创建子Agent-审核Agent", "POST", f"{BASE_URL}/sub-agents", 200, {
        "name": "审核Agent",
        "description": "负责文件审核",
        "system_prompt": "你是一个专业的文件审核专家，仔细检查文件内容的合规性。",
        "model_id": level_id1 or "test-model-level-id"
    })
    agent_id3 = r["id"] if r else None

    pause("sub_agents 表应该有 3 条")

    test("查询所有子Agent", "GET", f"{BASE_URL}/sub-agents", 200)

    if agent_id1:
        test("查询单个子Agent", "GET", f"{BASE_URL}/sub-agents/{agent_id1}", 200)

        test("更新子Agent", "PUT", f"{BASE_URL}/sub-agents/{agent_id1}", 200, {
            "description": "负责联网搜索和信息汇总-已更新"
        })
        test("验证更新", "GET", f"{BASE_URL}/sub-agents/{agent_id1}", 200)

    # 子Agent关联技能和工具
    if agent_id1 and skill_id1:
        print("\n  🔗 子Agent ← 技能")
        test("子Agent添加技能-搜索技能", "POST",
             f"{BASE_URL}/sub-agents/{agent_id1}/skills/{skill_id1}", 200)
        pause("sub_agents 表的 skill_ids 应该包含搜索技能ID")

    if agent_id1 and tool_id1:
        print("\n  🔗 子Agent ← 工具（直接关联）")
        test("子Agent添加工具-联网搜索", "POST",
             f"{BASE_URL}/sub-agents/{agent_id1}/tools/{tool_id1}", 200)
        pause("sub_agents 表的 tool_ids 应该包含联网搜索工具ID")

    if agent_id2 and tool_id3:
        test("报价Agent添加工具-报告workflow", "POST",
             f"{BASE_URL}/sub-agents/{agent_id2}/tools/{tool_id3}", 200)

    if agent_id3 and skill_id2:
        test("审核Agent添加技能-文件处理", "POST",
             f"{BASE_URL}/sub-agents/{agent_id3}/skills/{skill_id2}", 200)

    test("验证搜索Agent详情（应有skill_ids和tool_ids）", "GET",
         f"{BASE_URL}/sub-agents/{agent_id1}", 200)

    # ============================================================
    # 6. 角色
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 6. 角色 (roles)")
    print(f"{'='*60}")

    pause("准备创建角色（关联模型分级 + 子Agent）")

    r = test("创建角色-主管", "POST", f"{BASE_URL}/roles", 200, {
        "name": "supervisor",
        "business_knowledge": "保函业务知识：保函是银行应申请人要求向受益人开立的担保文件...",
        "system_prompt": "你是一个智能助手的主管，负责分析用户意图并将任务分配给合适的子Agent。",
        "main_model_id": level_id1 or "test-model-level-id",
        "fallback_model_id": level_id2 or "test-model-level-id-2"
    })
    role_id1 = r["id"] if r else None

    r = test("创建角色-客服", "POST", f"{BASE_URL}/roles", 200, {
        "name": "customer_service",
        "system_prompt": "你是一个友好的客服助手，帮助用户解答常见问题。",
        "main_model_id": level_id2 or "test-model-level-id"
    })
    role_id2 = r["id"] if r else None

    pause("roles 表应该有 2 条")

    test("查询所有角色", "GET", f"{BASE_URL}/roles", 200)

    if role_id1:
        test("查询单个角色", "GET", f"{BASE_URL}/roles/{role_id1}", 200)

        test("更新角色", "PUT", f"{BASE_URL}/roles/{role_id1}", 200, {
            "business_knowledge": "保函业务知识（更新版）：保函是银行应申请人要求向受益人开立的担保文件，包括投标保函、履约保函等。"
        })
        test("验证更新", "GET", f"{BASE_URL}/roles/{role_id1}", 200)

    # 角色关联子Agent
    if role_id1:
        print("\n  🔗 角色 ← 子Agent")
        if agent_id1:
            test("主管角色添加搜索Agent", "POST",
                 f"{BASE_URL}/roles/{role_id1}/sub-agents/{agent_id1}", 200)
        if agent_id2:
            test("主管角色添加报价Agent", "POST",
                 f"{BASE_URL}/roles/{role_id1}/sub-agents/{agent_id2}", 200)
        if agent_id3:
            test("主管角色添加审核Agent", "POST",
                 f"{BASE_URL}/roles/{role_id1}/sub-agents/{agent_id3}", 200)

        pause("roles 表的 sub_agent_ids 应该包含 3 个子Agent ID")

        test("验证主管角色详情", "GET", f"{BASE_URL}/roles/{role_id1}", 200)

    # ============================================================
    # 7. 场景
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 7. 场景 (scenes)")
    print(f"{'='*60}")

    pause("准备创建场景")

    r = test("创建场景-报价场景", "POST", f"{BASE_URL}/scenes", 200, {
        "scene_code": "quotation",
        "route_key": "quotation_flow",
        "report_config": {
            "workflow": {
                "file": {"template": "quotation_report.docx"},
                "data": {"source": "quotation_result"}
            }
        }
    })
    scene_id1 = r["id"] if r else None

    r = test("创建场景-审核场景", "POST", f"{BASE_URL}/scenes", 200, {
        "scene_code": "review",
        "route_key": "review_flow"
    })
    scene_id2 = r["id"] if r else None

    pause("scenes 表应该有 2 条")

    test("查询所有场景", "GET", f"{BASE_URL}/scenes", 200)

    test("按场景码查询-quotation", "GET", f"{BASE_URL}/scenes/code/quotation", 200)
    test("按场景码查询-不存在", "GET", f"{BASE_URL}/scenes/code/nonexistent", 404)

    if scene_id1:
        test("查询单个场景", "GET", f"{BASE_URL}/scenes/{scene_id1}", 200)

        test("更新场景", "PUT", f"{BASE_URL}/scenes/{scene_id1}", 200, {
            "route_key": "quotation_flow_v2"
        })
        test("验证更新", "GET", f"{BASE_URL}/scenes/{scene_id1}", 200)

    # 场景关联角色
    if scene_id1 and role_id1:
        print("\n  🔗 场景 ← 角色")
        test("报价场景添加主管角色", "POST",
             f"{BASE_URL}/scenes/{scene_id1}/roles/{role_id1}", 200)
        pause("scenes 表的 available_role_ids 应该包含主管角色ID")
        test("验证场景详情", "GET", f"{BASE_URL}/scenes/{scene_id1}", 200)

    if scene_id2 and role_id2:
        test("审核场景添加客服角色", "POST",
             f"{BASE_URL}/scenes/{scene_id2}/roles/{role_id2}", 200)

    # ============================================================
    # 8. 网关环境（单例）
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 8. 网关环境 (gateway_env) - 单例模式")
    print(f"{'='*60}")

    pause("网关环境只有一条记录")

    test("获取网关环境(可能为空)", "GET", f"{BASE_URL}/gateway-env", 200)

    test("设置网关环境", "PUT", f"{BASE_URL}/gateway-env", 200, {
        "port": 9000,
        "whitelist": ["127.0.0.1", "10.0.0.1"]
    })

    pause("gateway_env 表应该有 1 条")

    test("再次更新网关环境", "PUT", f"{BASE_URL}/gateway-env", 200, {
        "port": 9000,
        "whitelist": ["127.0.0.1", "10.0.0.1", "192.168.1.0/24"]
    })

    pause("应该还是只有 1 条，但 whitelist 多了一项")

    test("验证网关环境", "GET", f"{BASE_URL}/gateway-env", 200)

    # ============================================================
    # 9. 外部调用配置（auth_token 自动生成）
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 9. 外部调用配置 (gateway_apps) - token自动生成")
    print(f"{'='*60}")

    pause("准备创建外部调用配置（只传 app_id + available_scenes，token 自动生成）")

    r = test("创建外部调用配置-ERP系统", "POST", f"{BASE_URL}/gateway-apps", 200, {
        "app_id": "erp_system",
        "available_scenes": [
            {"scene_code": "quotation", "features": ["chat", "upload", "report"]},
            {"scene_code": "review", "features": ["chat", "upload"]}
        ]
    })
    app_config_id = r["id"] if r else None
    auto_token = r["auth_token"] if r else None

    if auto_token:
        print(f"\n  📝 自动生成的 auth_token: {auto_token}")

    pause("gateway_apps 表应该有 1 条，auth_token 是自动生成的随机字符串")

    r2 = test("创建外部调用配置-小程序", "POST", f"{BASE_URL}/gateway-apps", 200, {
        "app_id": "mini_program",
        "available_scenes": [
            {"scene_code": "quotation", "features": ["chat"]}
        ]
    })
    app_config_id2 = r2["id"] if r2 else None
    auto_token2 = r2["auth_token"] if r2 else None

    test("查询所有外部调用配置", "GET", f"{BASE_URL}/gateway-apps", 200)

    # 鉴权验证
    if auto_token:
        print("\n  🔐 鉴权验证")
        test("鉴权验证-正确token", "POST",
             f"{BASE_URL}/gateway-apps/validate?app_id=erp_system&token={auto_token}", 200)

        test("鉴权验证-错误token", "POST",
             f"{BASE_URL}/gateway-apps/validate?app_id=erp_system&token=wrong-token", 200)

        pause("第一个应该返回 valid:true，第二个 valid:false")

    test("鉴权验证-不存在的app", "POST",
         f"{BASE_URL}/gateway-apps/validate?app_id=nonexistent&token=xxx", 200)

    # ============================================================
    # 10. 渠道配置
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 10. 渠道配置 (gateway_channels)")
    print(f"{'='*60}")

    pause("准备创建渠道配置")

    r = test("创建企微渠道", "POST", f"{BASE_URL}/gateway-channels", 200, {
        "channel": "wechat_work",
        "enabled": True,
        "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
        "app_id": "wx-corp-001",
        "app_secret": "wx-secret-001",
        "config": {"agent_id": "1000001"}
    })
    channel_id1 = r["id"] if r else None

    r = test("创建飞书渠道", "POST", f"{BASE_URL}/gateway-channels", 200, {
        "channel": "feishu",
        "enabled": False,
        "webhook_url": "https://open.feishu.cn/xxx",
        "app_id": "cli_xxx",
        "app_secret": "fs-secret-001"
    })
    channel_id2 = r["id"] if r else None

    pause("gateway_channels 表应该有 2 条")

    test("查询所有渠道", "GET", f"{BASE_URL}/gateway-channels", 200)

    if channel_id1:
        test("更新渠道-禁用企微", "PUT", f"{BASE_URL}/gateway-channels/{channel_id1}", 200, {
            "enabled": False
        })
        pause("企微渠道的 enabled 应该变成 false")
        test("验证更新", "GET", f"{BASE_URL}/gateway-channels/{channel_id1}", 200)

    # ============================================================
    # 11. 文件处理配置
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 11. 文件处理 (file_processing)")
    print(f"{'='*60}")

    pause("准备创建文件处理配置")

    r = test("创建文件处理-保函", "POST", f"{BASE_URL}/file-processing", 200, {
        "file_type": "保函",
        "fields": ["beneficiary", "the_guaranteed", "types_of_guarantee",
                    "number", "project_name", "guarantee_amount", "bank"],
        "prompt": "# Role\n你是专业的数据抽取专家\n\n# Extraction Schema\n- beneficiary: 受益人\n- the_guaranteed: 被保证人\n- types_of_guarantee: 保函品种\n- number: 保函编号\n- project_name: 项目名称\n- guarantee_amount: 担保金额，单位：元\n- bank: 开函银行\n\n# Output\n返回JSON格式"
    })
    fp_id1 = r["id"] if r else None

    r = test("创建文件处理-合同", "POST", f"{BASE_URL}/file-processing", 200, {
        "file_type": "合同",
        "fields": ["party_a", "party_b", "contract_amount", "sign_date", "project_name"]
    })
    fp_id2 = r["id"] if r else None

    pause("file_processing 表应该有 2 条")

    test("查询所有文件处理配置", "GET", f"{BASE_URL}/file-processing", 200)

    if fp_id1:
        test("查询单个文件处理配置", "GET", f"{BASE_URL}/file-processing/{fp_id1}", 200)

        test("更新-增加抽取要素", "PUT", f"{BASE_URL}/file-processing/{fp_id1}", 200, {
            "fields": ["beneficiary", "the_guaranteed", "types_of_guarantee",
                        "number", "project_name", "guarantee_amount", "bank", "validity_period"]
        })
        pause("fields 里应该多了 validity_period")
        test("验证更新", "GET", f"{BASE_URL}/file-processing/{fp_id1}", 200)

    # ============================================================
    # 12. 会话日志
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 12. 会话日志 (chat_logs)")
    print(f"{'='*60}")

    pause("准备测试会话日志（含新增的耗时和token字段）")

    # 注意：chat_logs 没有独立的 POST 接口（通过 ChatLogService.log() 内部写入）
    # 但通用工厂注册了吗？看 config_api.py —— 没有注册 chat_logs 的 CRUD
    # 所以只能测查询接口

    # 先通过内部方式插入测试数据（直接调 POST 如果有的话）
    # config_api.py 里没有注册 chat_logs 的通用 CRUD，只有查询接口
    # 我们直接测查询接口（空数据也应该返回 200）

    test("按会话查日志(空)", "GET", f"{BASE_URL}/chat-logs/session/test-session-001", 200)
    test("按应用查日志(空)", "GET", f"{BASE_URL}/chat-logs/app/erp_system", 200)

    pause("应该都返回空列表 []")

    # ============================================================
    # 13. 完整关联链路验证
    # ============================================================
    print(f"\n{'='*60}")
    print("🔗 13. 完整关联链路验证")
    print(f"{'='*60}")

    pause("验证完整链路：Scene → Role → SubAgent → Skill → Tool → ModelLevel → ModelConnection")

    print("\n  📊 关联链路数据汇总：")
    print(f"     ModelConnection: {conn_id}, {conn_id2}")
    print(f"     ModelLevel: {level_id1}(主力), {level_id2}(备用), {level_id3}(兜底)")
    print(f"     Tool: {tool_id1}(搜索), {tool_id2}(OCR), {tool_id3}(workflow), {tool_id4}(禁用)")
    print(f"     Skill: {skill_id1}(搜索技能), {skill_id2}(文件处理技能)")
    print(f"     SubAgent: {agent_id1}(搜索), {agent_id2}(报价), {agent_id3}(审核)")
    print(f"     Role: {role_id1}(主管), {role_id2}(客服)")
    print(f"     Scene: {scene_id1}(报价), {scene_id2}(审核)")
    print(f"     GatewayApp: {app_config_id}(ERP), {app_config_id2}(小程序)")

    # 验证场景 → 角色 → 子Agent 链路
    if scene_id1:
        print("\n  🔍 验证报价场景完整链路：")
        scene_data = test("查询报价场景", "GET", f"{BASE_URL}/scenes/{scene_id1}", 200)
        if scene_data:
            role_ids = scene_data.get("available_role_ids", [])
            print(f"     场景关联角色: {role_ids}")

            for rid in role_ids:
                role_data = test(f"查询角色 {rid}", "GET", f"{BASE_URL}/roles/{rid}", 200)
                if role_data:
                    sa_ids = role_data.get("sub_agent_ids", [])
                    print(f"     角色 {role_data.get('name')} 关联子Agent: {sa_ids}")

                    for said in sa_ids:
                        sa_data = test(f"查询子Agent {said}", "GET",
                                       f"{BASE_URL}/sub-agents/{said}", 200)
                        if sa_data:
                            print(f"       子Agent {sa_data.get('name')}: "
                                  f"skills={sa_data.get('skill_ids', [])}, "
                                  f"tools={sa_data.get('tool_ids', [])}, "
                                  f"model={sa_data.get('model_id')}")

    pause("链路验证完成，准备测试解除关联")

    # ============================================================
    # 14. 解除关联测试
    # ============================================================
    print(f"\n{'='*60}")
    print("🔗 14. 解除关联测试")
    print(f"{'='*60}")

    if scene_id1 and role_id1:
        test("场景移除角色", "DELETE",
             f"{BASE_URL}/scenes/{scene_id1}/roles/{role_id1}", 200)
        r = test("验证场景", "GET", f"{BASE_URL}/scenes/{scene_id1}", 200)
        if r:
            assert r.get("available_role_ids") == [], \
                f"expected empty, got {r.get('available_role_ids')}"
            print("     ✅ available_role_ids 已清空")

    if role_id1 and agent_id1:
        test("角色移除子Agent-搜索", "DELETE",
             f"{BASE_URL}/roles/{role_id1}/sub-agents/{agent_id1}", 200)

    if agent_id1 and skill_id1:
        test("子Agent移除技能", "DELETE",
             f"{BASE_URL}/sub-agents/{agent_id1}/skills/{skill_id1}", 200)

    if agent_id1 and tool_id1:
        test("子Agent移除工具", "DELETE",
             f"{BASE_URL}/sub-agents/{agent_id1}/tools/{tool_id1}", 200)

    if skill_id1 and tool_id1:
        test("技能移除工具", "DELETE",
             f"{BASE_URL}/skills/{skill_id1}/tools/{tool_id1}", 200)

    if agent_id1:
        r = test("验证搜索Agent（应该都清空了）", "GET",
                 f"{BASE_URL}/sub-agents/{agent_id1}", 200)
        if r:
            print(f"     skill_ids: {r.get('skill_ids', [])}")
            print(f"     tool_ids: {r.get('tool_ids', [])}")

    pause("关联都解除了")

    # ============================================================
    # 15. 清理所有测试数据
    # ============================================================
    print(f"\n{'='*60}")
    print("🧹 15. 清理所有测试数据")
    print(f"{'='*60}")

    pause("准备清理所有测试数据（按依赖倒序删除）")

    # 按依赖倒序清理：场景 → 角色 → 子Agent → 技能 → 工具 → 模型分级 → 模型连接 → 网关
    cleanup_all("scenes")
    cleanup_all("roles")
    cleanup_all("sub-agents")
    cleanup_all("skills")
    cleanup_all("tools")
    cleanup_all("model-levels")
    cleanup_all("model-connections")
    cleanup_all("gateway-apps")
    cleanup_all("gateway-channels")
    cleanup_all("file-processing")

    # gateway-env 不清理（单例，留着）

    pause("所有测试数据已清理，去 Database Client 确认各表为空")

    # ============================================================
    # 结果汇总
    # ============================================================
    print(f"\n{'='*60}")
    print(f"🏁 测试完成")
    print(f"{'='*60}")
    print(f"  ✅ 通过: {passed}")
    print(f"  ❌ 失败: {failed}")

    if errors:
        print(f"\n  失败详情:")
        for e in errors:
            print(f"    - {e}")

    if failed == 0:
        print("\n  🎉 全部通过！配置接口验证完成。")
    else:
        print("\n  ⚠️  有失败项，需要修复后再提交。")

    print(f"\n  📊 测试覆盖:")
    print(f"     - 12 个配置表的 CRUD")
    print(f"     - 5 组关联关系（Scene↔Role↔SubAgent↔Skill↔Tool）")
    print(f"     - 特殊接口（单例、token自动生成、降级链、启用工具、场景码查询）")
    print(f"     - 鉴权验证（正确/错误/不存在）")
    print(f"     - 关联建立 + 解除")
    print(f"     - 数据清理")
