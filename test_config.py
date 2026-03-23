# -*- coding: utf-8 -*-
"""
配置接口CRUD测试（交互式，逐步执行）
运行：python test_config.py
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
            print(f"✅ {name}")
            if r.text:
                data = r.json()
                print(f"     响应: {json.dumps(data, ensure_ascii=False, indent=2)[:2000]}")
                return data
            return None
        else:
            failed += 1
            errors.append(f"{name}: 期望{expected_status}, 实际{r.status_code}")
            print(f"  ❌ {name} (期望{expected_status}, 实际{r.status_code})")
            print(f"     响应: {r.text[:300]}")
            return None
    except Exception as e:
        failed += 1
        errors.append(f"{name}: 异常 {e}")
        print(f"  ❌ {name} (异常: {e})")
        return None


if __name__ == "__main__":
    print("🚀 配置接口CRUD交互式测试")
    print("每一步会暂停，你可以去Database Client查看数据变化\n")

    # ============================================================
    # 1. 模型连接
    # ============================================================
    print(f"\n{'='*50}")
    print("📦 模型连接 (model_connections)")
    print(f"{'='*50}")

    pause("准备创建一条模型连接，去Database Client打开model_connections表")

    result = test("创建模型连接", "POST", f"{BASE_URL}/model-connections", 200, {
        "protocol": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-test-key-123",
        "models": ["gpt-4", "gpt-3.5-turbo"],
        "description": "OpenAI官方"
    })
    conn_id = result["id"] if result else None

    pause("刷新Database Client，应该能看到model_connections表里多了一条数据")

    test("查询所有模型连接", "GET", f"{BASE_URL}/model-connections", 200)

    pause("看看返回的列表数据")

    if conn_id:
        test("查询单个模型连接", "GET", f"{BASE_URL}/model-connections/{conn_id}", 200)

        pause("准备更新这条模型连接")

        test("更新模型连接", "PUT", f"{BASE_URL}/model-connections/{conn_id}", 200, {
            "description": "OpenAI官方-已更新",
            "models": ["gpt-4", "gpt-3.5-turbo", "gpt-4o"]
        })

        pause("刷新Database Client，看看data字段里的description和models是否变了")

        test("验证更新结果", "GET", f"{BASE_URL}/model-connections/{conn_id}", 200)

        pause("准备删除这条模型连接")

        test("删除模型连接", "DELETE", f"{BASE_URL}/model-connections/{conn_id}", 200)

        pause("刷新Database Client，这条数据应该没了")

        test("验证删除(应该404)", "GET", f"{BASE_URL}/model-connections/{conn_id}", 404)

    test("查询不存在的(应该404)", "GET", f"{BASE_URL}/model-connections/fake-id-999", 404)
    test("删除不存在的(应该404)", "DELETE", f"{BASE_URL}/model-connections/fake-id-999", 404)

    # ============================================================
    # 2. 模型分级
    # ============================================================
    print(f"\n{'='*50}")
    print("📦 模型分级 (model_levels)")
    print(f"{'='*50}")

    pause("准备测试模型分级")

    result = test("创建模型分级", "POST", f"{BASE_URL}/model-levels", 200, {
        "name": "主力模型",
        "level": 10,
        "connection_id": "test-conn-id",
        "model": "gpt-4",
        "max_retry": 3,
        "timeout": 30
    })
    level_id = result["id"] if result else None

    pause("刷新Database Client，看model_levels表")

    if level_id:
        test("更新模型分级", "PUT", f"{BASE_URL}/model-levels/{level_id}", 200, {
            "name": "主力模型-已更新",
            "max_retry": 5
        })

        pause("看看更新后的数据")

        test("验证更新", "GET", f"{BASE_URL}/model-levels/{level_id}", 200)

    #创建多个分级测试降级链
    test("创建备用模型", "POST", f"{BASE_URL}/model-levels", 200, {
        "name": "备用模型",
        "level": 2,
        "connection_id": "test-conn-id",
        "model": "gpt-3.5-turbo",
        "max_retry": 3,
        "timeout": 20
    })
    test("创建兜底模型", "POST", f"{BASE_URL}/model-levels", 200, {
        "name": "兜底模型",
        "level": 3,
        "connection_id": "test-conn-id",
        "model": "gpt-3.5",
        "max_retry": 5,
        "timeout": 60
    })

    pause("现在有3条模型分级，准备测试降级链查询")

    test("获取模型降级链(按level排序)", "GET", f"{BASE_URL}/model-levels/fallback-chain", 200)

    pause("看看返回的顺序是不是 level 1→2→3")

    #清理
    all_levels = requests.get(f"{BASE_URL}/model-levels").json()
    for item in all_levels:
        requests.delete(f"{BASE_URL}/model-levels/{item['_id']}")
    print("  🧹 已清理所有模型分级数据")

    # ============================================================
    # 3. 工具
    # ============================================================
    print(f"\n{'='*50}")
    print("📦 工具 (tools)")
    print(f"{'='*50}")

    pause("准备测试工具CRUD")

    result1 = test("创建工具-联网搜索", "POST", f"{BASE_URL}/tools", 200, {
        "name": "联网搜索",
        "type": "mcp",
        "category": "web_search",
        "url": "https://search.example.com",
        "enabled": True,
        "description": "搜索引擎"
    })
    tool_id1 = result1["id"] if result1 else None

    result2 = test("创建工具-OCR", "POST", f"{BASE_URL}/tools", 200, {
        "name": "OCR识别",
        "type": "http",
        "category": "ocr",
        "url": "http://localhost:8001/ocr/process",
        "enabled": True,
        "description": "图片文字识别"
    })

    result3 = test("创建工具-已禁用", "POST", f"{BASE_URL}/tools", 200, {
        "name": "报价计算",
        "type": "http",
        "category": "api",
        "enabled": False,
        "description": "暂未启用"
    })

    pause("刷新Database Client，tools表应该有3条数据")

    test("查询启用的工具", "GET", f"{BASE_URL}/tools/enabled", 200)

    pause("应该只返回2条（联网搜索和OCR）")

    test("按类型查工具-mcp", "GET", f"{BASE_URL}/tools/type/mcp", 200)

    pause("应该只返回1条（联网搜索）")

    if tool_id1:
        test("更新工具", "PUT", f"{BASE_URL}/tools/{tool_id1}", 200, {
            "description": "搜索引擎-已更新",
            "enabled": False
        })

        pause("联网搜索现在被禁用了，再查启用工具")

        test("再查启用工具", "GET", f"{BASE_URL}/tools/enabled", 200)

        pause("应该只剩1条（OCR）")

    #清理
    all_tools = requests.get(f"{BASE_URL}/tools").json()
    for item in all_tools:
        requests.delete(f"{BASE_URL}/tools/{item['_id']}")
    print("  🧹 已清理所有工具数据")

    # ============================================================
    # 4. 网关环境（单例）
    # ============================================================
    print(f"\n{'='*50}")
    print("📦 网关环境 (gateway_env) - 单例模式")
    print(f"{'='*50}")

    pause("网关环境只有一条记录，测试创建和更新")

    test("获取网关环境(可能为空)", "GET", f"{BASE_URL}/gateway-env", 200)

    test("设置网关环境", "PUT", f"{BASE_URL}/gateway-env", 200, {
        "port": 8080,
        "whitelist": ["127.0.0.1", "10.0.0.1"]
    })

    pause("刷新Database Client，gateway_env表应该有1条")

    test("再次更新网关环境", "PUT", f"{BASE_URL}/gateway-env", 200, {
        "port": 9090,
        "whitelist": ["127.0.0.1"]
    })

    pause("应该还是只有1条，但port变成了9090")

    test("验证网关环境", "GET", f"{BASE_URL}/gateway-env", 200)

    # ============================================================
    # 5. 外部调用配置
    # ============================================================
    print(f"\n{'='*50}")
    print("📦 外部调用配置 (gateway_apps)")
    print(f"{'='*50}")

    pause("准备测试外部调用配置和鉴权验证")

    result = test("创建外部调用配置", "POST", f"{BASE_URL}/gateway-apps", 200, {
        "app_id": "APP_001",
        "auth_token": "secret-token-abc",
        "available_scenes": ["SCENE_001", "SCENE_002"]
    })
    app_config_id = result["id"] if result else None

    pause("刷新Database Client看数据")

    test("鉴权验证-正确token", "POST",
         f"{BASE_URL}/gateway-apps/validate?app_id=APP_001&token=secret-token-abc", 200)

    test("鉴权验证-错误token", "POST",
         f"{BASE_URL}/gateway-apps/validate?app_id=APP_001&token=wrong-token", 200)

    pause("第一个应该返回valid:true，第二个valid:false")

    if app_config_id:
        requests.delete(f"{BASE_URL}/gateway-apps/{app_config_id}")
        print("  🧹 已清理外部调用配置")

    # ============================================================
    # 6. 渠道配置
    # ============================================================
    print(f"\n{'='*50}")
    print("📦 渠道配置 (gateway_channels)")
    print(f"{'='*50}")

    pause("准备测试渠道配置")

    result = test("创建企微渠道", "POST", f"{BASE_URL}/gateway-channels", 200, {
        "channel": "wechat_work",
        "enabled": True,
        "webhook_url": "https://qyapi.weixin.qq.com/xxx",
        "app_id": "wx-001"
    })
    channel_id = result["id"] if result else None

    pause("刷新Database Client看数据")

    if channel_id:
        test("更新渠道-禁用", "PUT", f"{BASE_URL}/gateway-channels/{channel_id}", 200, {
            "enabled": False
        })

        pause("enabled应该变成false了")

        requests.delete(f"{BASE_URL}/gateway-channels/{channel_id}")
        print("  🧹 已清理渠道配置")

    # ============================================================
    # 7. 关联关系测试
    # ============================================================
    print(f"\n{'='*50}")
    print("🔗 关联关系测试")
    print(f"{'='*50}")

    pause("准备创建一组关联数据：工具→技能→子Agent→角色→场景")

    # 创建工具
    r = test("创建工具", "POST", f"{BASE_URL}/tools", 200, {
        "name": "联网搜索", "type": "mcp", "category": "web_search", "enabled": True
    })
    tool_id = r["id"] if r else None

    # 创建技能
    r = test("创建技能", "POST", f"{BASE_URL}/skills", 200, {
        "name": "搜索技能", "description": "联网搜索能力"
    })
    skill_id = r["id"] if r else None

    # 创建子Agent
    r = test("创建子Agent", "POST", f"{BASE_URL}/sub-agents", 200, {
        "name": "搜索Agent", "system_prompt": "你是搜索助手", "model_id": "test-model"
    })
    agent_id = r["id"] if r else None

    # 创建角色
    r = test("创建角色", "POST", f"{BASE_URL}/roles", 200, {
        "name": "主角色", "system_prompt": "你是助手", "main_model_id": "test-model"
    })
    role_id = r["id"] if r else None

    # 创建场景
    r = test("创建场景", "POST", f"{BASE_URL}/scenes", 200, {
        "scene_code": "TEST_SCENE"
    })
    scene_id = r["id"] if r else None

    pause("5条数据都创建好了，去各个表看看")

    if all([tool_id, skill_id, agent_id, role_id, scene_id]):

        # --- 技能 ← 工具 ---
        print("\n  🔗 技能 ← 工具")
        test("技能添加工具", "POST", f"{BASE_URL}/skills/{skill_id}/tools/{tool_id}", 200)

        # 注意：技能添加工具的接口还没有，需要先检查
        # 如果没有这个接口，用更新的方式
        pause("去skills表看skill的tool_ids字段是否包含了工具ID")

        # --- 子Agent ← 技能 ---
        print("\n  🔗 子Agent ← 技能")
        test("子Agent添加技能", "POST", f"{BASE_URL}/sub-agents/{agent_id}/skills/{skill_id}", 200)

        pause("去sub_agents表看skill_ids字段")

        test("查看子Agent详情", "GET", f"{BASE_URL}/sub-agents/{agent_id}", 200)

        # --- 子Agent ← 工具 ---
        print("\n  🔗 子Agent ← 工具")
        test("子Agent添加工具", "POST", f"{BASE_URL}/sub-agents/{agent_id}/tools/{tool_id}", 200)

        pause("去sub_agents表看tool_ids字段，现在应该同时有skill_ids和tool_ids")

        test("查看子Agent详情", "GET", f"{BASE_URL}/sub-agents/{agent_id}", 200)

        # --- 角色 ← 子Agent ---
        print("\n  🔗 角色 ← 子Agent")
        test("角色添加子Agent", "POST", f"{BASE_URL}/roles/{role_id}/sub-agents/{agent_id}", 200)

        pause("去roles表看sub_agent_ids字段")

        test("查看角色详情", "GET", f"{BASE_URL}/roles/{role_id}", 200)

        # --- 场景 ← 角色 ---
        print("\n  🔗 场景 ← 角色")
        test("场景添加角色", "POST", f"{BASE_URL}/scenes/{scene_id}/roles/{role_id}", 200)

        pause("去scenes表看available_role_ids字段")

        test("查看场景详情", "GET", f"{BASE_URL}/scenes/{scene_id}", 200)

        pause("现在完整链路：场景→角色→子Agent→技能→工具 全部关联好了\n准备逐步解除关联")

        # --- 解除关联 ---
        test("场景移除角色", "DELETE", f"{BASE_URL}/scenes/{scene_id}/roles/{role_id}", 200)
        pause("scenes表的available_role_ids应该为空了")

        test("角色移除子Agent", "DELETE", f"{BASE_URL}/roles/{role_id}/sub-agents/{agent_id}", 200)
        pause("roles表的sub_agent_ids应该为空了")

        test("子Agent移除技能", "DELETE", f"{BASE_URL}/sub-agents/{agent_id}/skills/{skill_id}", 200)
        test("子Agent移除工具", "DELETE", f"{BASE_URL}/sub-agents/{agent_id}/tools/{tool_id}", 200)
        pause("sub_agents表的skill_ids和tool_ids都应该为空了")

        #清理
        pause("准备清理所有测试数据")
        requests.delete(f"{BASE_URL}/scenes/{scene_id}")
        requests.delete(f"{BASE_URL}/roles/{role_id}")
        requests.delete(f"{BASE_URL}/sub-agents/{agent_id}")
        requests.delete(f"{BASE_URL}/skills/{skill_id}")
        requests.delete(f"{BASE_URL}/tools/{tool_id}")
        print("  🧹 已清理所有关联测试数据")

    # ============================================================
    # 8. 文件处理配置
    # ============================================================
    print(f"\n{'='*50}")
    print("📦 文件处理 (file_processing)")
    print(f"{'='*50}")

    pause("准备测试文件处理配置")

    result = test("创建文件处理配置", "POST", f"{BASE_URL}/file-processing", 200, {
        "file_type": "pdf",
        "fields": ["投保人", "被保人", "保额", "保费"]
    })
    fp_id = result["id"] if result else None

    pause("刷新Database Client看数据")

    if fp_id:
        test("更新-增加抽取要素", "PUT", f"{BASE_URL}/file-processing/{fp_id}", 200, {
            "fields": ["投保人", "被保人", "保额", "保费", "生效日期"]
        })

        pause("fields里应该多了'生效日期'")

        test("验证更新", "GET", f"{BASE_URL}/file-processing/{fp_id}", 200)

        requests.delete(f"{BASE_URL}/file-processing/{fp_id}")
        print("  🧹 已清理文件处理配置")

    # ============================================================
    # 结果汇总
    # ============================================================
    print(f"\n{'='*50}")
    print(f"🏁 测试完成")
    print(f"{'='*50}")
    print(f"✅ 通过: {passed}")
    print(f"❌ 失败: {failed}")

    if errors:
        print(f"\n失败详情:")
        for e in errors:
            print(f"  - {e}")

    if failed == 0:
        print("\n🎉 全部通过！可以提交分支了。")
    else:
        print("\n⚠️  有失败项，需要修复后再提交。")
