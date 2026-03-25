# -*- coding: utf-8 -*-
"""
业务表 app_id 隔离测试
运行：python test_app_isolation.py

测试 FileService / SessionService / MemoryService 的 app_id 隔离
直接调用 Service 层，不走 HTTP 接口
"""
import sys
from datetime import datetime
from dataBase.database import Database
from dataBase.Service import FileService, SessionService, MemoryService
from dataBase.Schema import FileModel

# 初始化数据库连接
Database.connect()

passed = 0
failed = 0
errors = []

# 测试常量
APP_A = "test_app_alpha"
APP_B = "test_app_beta"
SESSION_A = "test_session_alpha_001"
SESSION_B = "test_session_beta_001"
SESSION_SHARED = "test_session_shared_001"


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        msg = f"{name}: {detail}" if detail else name
        errors.append(msg)
        print(f"  ❌ {name}")
        if detail:
            print(f"     {detail}")


def make_file(file_id: str, file_name: str, app_id: str = "") -> FileModel:
    return FileModel(
        app_id=app_id,
        file_id=file_id,
        file_name=file_name,
        file_type=["测试文件"],
        content=f"这是 {app_id} 的测试文件内容: {file_name}",
        main_info={"test_key": f"value_from_{app_id}"},
        upload_time=datetime.now(),
    )


if __name__ == "__main__":
    print("🚀 业务表 app_id 隔离测试")
    print(f"   APP_A = {APP_A}")
    print(f"   APP_B = {APP_B}\n")

    file_service = FileService()
    session_service = SessionService()
    memory_service = MemoryService()

    # ============================================================
    # 清理：先删掉可能残留的测试数据
    # ============================================================
    print(f"{'='*60}")
    print("🧹 0. 清理残留测试数据")
    print(f"{'='*60}")

    for sid in [SESSION_A, SESSION_B, SESSION_SHARED]:
        session_service.delete_everything_about_session(sid)

    for fid in [
        "test_file_a1", "test_file_a2",
        "test_file_b1", "test_file_b2",
        "test_file_no_app",
    ]:
        file_service.delete_file_info(fid)

    print("  🧹 清理完成\n")

    # ============================================================
    # 1. FileService 隔离
    # ============================================================
    print(f"{'='*60}")
    print("📦 1. FileService — 文件隔离")
    print(f"{'='*60}")

    # 创建 APP_A 的文件
    file_a1 = make_file("test_file_a1", "alpha_doc1.pdf", APP_A)
    file_a2 = make_file("test_file_a2", "alpha_doc2.pdf", APP_A)
    file_service.save_file_info(file_a1)
    file_service.save_file_info(file_a2)

    # 创建 APP_B 的文件
    file_b1 = make_file("test_file_b1", "beta_doc1.pdf", APP_B)
    file_b2 = make_file("test_file_b2", "beta_doc2.pdf", APP_B)
    file_service.save_file_info(file_b1)
    file_service.save_file_info(file_b2)

    # 创建无 app_id 的文件（兼容性）
    file_no_app = make_file("test_file_no_app", "no_app_doc.pdf", "")
    file_service.save_file_info(file_no_app)

    print("\n  --- get_file_info 隔离 ---")

    # APP_A 能查到自己的文件
    result = file_service.get_file_info("test_file_a1", app_id=APP_A)
    check("APP_A 查自己的文件 → 找到", result is not None)

    # APP_A 查不到 APP_B 的文件
    result = file_service.get_file_info("test_file_b1", app_id=APP_A)
    check("APP_A 查 APP_B 的文件 → 找不到", result is None)

    # APP_B 查不到 APP_A 的文件
    result = file_service.get_file_info("test_file_a1", app_id=APP_B)
    check("APP_B 查 APP_A 的文件 → 找不到", result is None)

    # APP_B 能查到自己的文件
    result = file_service.get_file_info("test_file_b1", app_id=APP_B)
    check("APP_B 查自己的文件 → 找到", result is not None)

    # 不传 app_id 时能查到任何文件（兼容旧逻辑）
    result = file_service.get_file_info("test_file_a1", app_id=None)
    check("不传 app_id 查文件 → 找到（兼容模式）", result is not None)

    result = file_service.get_file_info("test_file_b1", app_id=None)
    check("不传 app_id 查 APP_B 文件 → 找到（兼容模式）", result is not None)

    print("\n  --- get_files_by_app 隔离 ---")

    files_a = file_service.get_files_by_app(APP_A)
    check(f"APP_A 的文件数量 == 2", len(files_a) == 2,
          f"实际: {len(files_a)}")

    files_b = file_service.get_files_by_app(APP_B)
    check(f"APP_B 的文件数量 == 2", len(files_b) == 2,
          f"实际: {len(files_b)}")

    # APP_A 的文件列表里不包含 APP_B 的文件
    file_ids_a = [f.get("file_id") for f in files_a]
    check("APP_A 文件列表不含 APP_B 文件",
          "test_file_b1" not in file_ids_a and "test_file_b2" not in file_ids_a,
          f"实际文件ID: {file_ids_a}")

    files_empty = file_service.get_files_by_app("")
    check(f"空 app_id 的文件数量 == 1", len(files_empty) == 1,
          f"实际: {len(files_empty)}")

    # ============================================================
    # 2. SessionService 隔离
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 2. SessionService — 会话隔离")
    print(f"{'='*60}")

    # 通过 add_file_to_session 创建会话（会自动创建 session）
    session_service.add_file_to_session(SESSION_A, file_a1, app_id=APP_A)
    session_service.add_file_to_session(SESSION_A, file_a2, app_id=APP_A)
    session_service.add_file_to_session(SESSION_B, file_b1, app_id=APP_B)

    print("\n  --- get_session 隔离 ---")

    # APP_A 能查到自己的会话
    sess = session_service.get_session(SESSION_A, app_id=APP_A)
    check("APP_A 查自己的会话 → 找到", sess is not None)
    if sess:
        check("APP_A 会话有 2 个文件", len(sess.file_list) == 2,
              f"实际: {len(sess.file_list)}")

    # APP_A 查不到 APP_B 的会话
    sess = session_service.get_session(SESSION_B, app_id=APP_A)
    check("APP_A 查 APP_B 的会话 → 找不到", sess is None)

    # APP_B 查不到 APP_A 的会话
    sess = session_service.get_session(SESSION_A, app_id=APP_B)
    check("APP_B 查 APP_A 的会话 → 找不到", sess is None)

    # 不传 app_id 时能查到（兼容模式）
    sess = session_service.get_session(SESSION_A, app_id=None)
    check("不传 app_id 查会话 → 找到（兼容模式）", sess is not None)

    print("\n  --- get_sessions_by_app 隔离 ---")

    sessions_a = session_service.get_sessions_by_app(APP_A)
    check(f"APP_A 的会话数量 == 1", len(sessions_a) == 1,
          f"实际: {len(sessions_a)}")

    sessions_b = session_service.get_sessions_by_app(APP_B)
    check(f"APP_B 的会话数量 == 1", len(sessions_b) == 1,
          f"实际: {len(sessions_b)}")

    print("\n  --- get_session_files_content 隔离 ---")

    # APP_A 查自己会话的文件内容
    files_content = session_service.get_session_files_content(SESSION_A, app_id=APP_A)
    check("APP_A 查自己会话的文件内容 → 有数据", len(files_content) > 0,
          f"实际: {len(files_content)}")

    # APP_B 查 APP_A 会话的文件内容 → 空
    files_content = session_service.get_session_files_content(SESSION_A, app_id=APP_B)
    check("APP_B 查 APP_A 会话的文件内容 → 空", len(files_content) == 0,
          f"实际: {len(files_content)}")

    # ============================================================
    # 3. MemoryService 隔离
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 3. MemoryService — 记忆隔离")
    print(f"{'='*60}")

    # APP_A 写入记忆
    memory_service.save_memory(SESSION_A, "user", "APP_A 的用户消息1", app_id=APP_A)
    memory_service.save_memory(SESSION_A, "assistant", "APP_A 的助手回复1", app_id=APP_A)
    memory_service.save_memory(SESSION_A, "user", "APP_A 的用户消息2", app_id=APP_A)

    # APP_B 写入记忆（故意用同一个 session_id，测试 app_id 隔离）
    memory_service.save_memory(SESSION_A, "user", "APP_B 冒充的消息", app_id=APP_B)

    print("\n  --- get_recent_memories 隔离 ---")

    # APP_A 查自己的记忆
    mems_a = memory_service.get_recent_memories(SESSION_A, last_n=10, app_id=APP_A)
    check(f"APP_A 的记忆数量 == 3", len(mems_a) == 3,
          f"实际: {len(mems_a)}")

    # 验证内容不包含 APP_B 的消息
    contents_a = [m.get("content", "") for m in mems_a]
    check("APP_A 记忆不含 APP_B 的消息",
          "APP_B 冒充的消息" not in contents_a,
          f"实际内容: {contents_a}")

    # APP_B 查同一个 session_id 的记忆
    mems_b = memory_service.get_recent_memories(SESSION_A, last_n=10, app_id=APP_B)
    check(f"APP_B 查同 session_id 的记忆 == 1", len(mems_b) == 1,
          f"实际: {len(mems_b)}")

    # 不传 app_id 时查到所有（兼容模式）
    mems_all = memory_service.get_recent_memories(SESSION_A, last_n=10, app_id=None)
    check(f"不传 app_id 查记忆 == 4（全部）", len(mems_all) == 4,
          f"实际: {len(mems_all)}")

    # ============================================================
    # 4. SessionService 联动 — append_chat_message + get_full_context
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 4. 联动测试 — append_chat_message + get_full_context")
    print(f"{'='*60}")

    # 通过 SessionService 追加聊天消息
    session_service.append_chat_message(SESSION_A, "user", "联动测试消息", app_id=APP_A)

    # 获取完整上下文
    ctx_a = session_service.get_full_context(SESSION_A, last_n=20, app_id=APP_A)
    check("get_full_context 返回 history", "history" in ctx_a)
    check("get_full_context 返回 files", "files" in ctx_a)

    history_a = ctx_a.get("history", [])
    check(f"APP_A 完整上下文 history 数量 == 4（3条原始+1条联动）",
          len(history_a) == 4,
          f"实际: {len(history_a)}")

    files_a = ctx_a.get("files", [])
    check(f"APP_A 完整上下文 files 数量 == 2",
          len(files_a) == 2,
          f"实际: {len(files_a)}")

    # APP_B 获取同 session_id 的上下文
    ctx_b = session_service.get_full_context(SESSION_A, last_n=20, app_id=APP_B)
    history_b = ctx_b.get("history", [])
    files_b = ctx_b.get("files", [])
    check(f"APP_B 查同 session_id 的 history == 1",
          len(history_b) == 1,
          f"实际: {len(history_b)}")
    check(f"APP_B 查同 session_id 的 files == 0",
          len(files_b) == 0,
          f"实际: {len(files_b)}")

    # ============================================================
    # 5. 边界情况
    # ============================================================
    print(f"\n{'='*60}")
    print("📦 5. 边界情况")
    print(f"{'='*60}")

    # 不存在的 app_id
    files_none = file_service.get_files_by_app("nonexistent_app")
    check("不存在的 app_id 查文件 → 空列表", len(files_none) == 0)

    sessions_none = session_service.get_sessions_by_app("nonexistent_app")
    check("不存在的 app_id 查会话 → 空列表", len(sessions_none) == 0)

    mems_none = memory_service.get_recent_memories("nonexistent_session", app_id="nonexistent_app")
    check("不存在的 session+app 查记忆 → 空列表", len(mems_none) == 0)

    # 重复保存同一文件（幂等性）
    dup_id = file_service.save_file_info(file_a1)
    check("重复保存文件 → 返回已有 ID", dup_id == "test_file_a1",
          f"实际: {dup_id}")

    files_a_after = file_service.get_files_by_app(APP_A)
    check("重复保存后文件数量不变 == 2", len(files_a_after) == 2,
          f"实际: {len(files_a_after)}")

    # 同一会话重复添加同一文件（幂等性）
    session_service.add_file_to_session(SESSION_A, file_a1, app_id=APP_A)
    sess_after = session_service.get_session(SESSION_A, app_id=APP_A)
    check("重复添加文件到会话 → file_list 不重复",
          sess_after is not None and len(sess_after.file_list) == 2,
          f"实际 file_list: {sess_after.file_list if sess_after else 'None'}")

    # ============================================================
    # 6. 清理测试数据
    # ============================================================
    print(f"\n{'='*60}")
    print("🧹 6. 清理测试数据")
    print(f"{'='*60}")

    for sid in [SESSION_A, SESSION_B, SESSION_SHARED]:
        session_service.delete_everything_about_session(sid)
        print(f"  🧹 已清理会话: {sid}")

    # 清理 APP_B 在 SESSION_A 里写的记忆（delete_everything_about_session 按 session_id 删，会一起删掉）
    # 但 APP_B 的记忆也在 SESSION_A 里，已经被上面删掉了

    for fid in [
        "test_file_a1", "test_file_a2",
        "test_file_b1", "test_file_b2",
        "test_file_no_app",
    ]:
        file_service.delete_file_info(fid)
        print(f"  🧹 已清理文件: {fid}")

    # 验证清理干净
    files_a_final = file_service.get_files_by_app(APP_A)
    files_b_final = file_service.get_files_by_app(APP_B)
    check("清理后 APP_A 文件数 == 0", len(files_a_final) == 0,
          f"实际: {len(files_a_final)}")
    check("清理后 APP_B 文件数 == 0", len(files_b_final) == 0,
          f"实际: {len(files_b_final)}")

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
        print("\n  🎉 全部通过！app_id 隔离验证完成。")
    else:
        print("\n  ⚠️  有失败项，需要检查 Service.py 的 app_id 过滤逻辑。")

    print(f"\n  📊 测试覆盖:")
    print(f"     - FileService: get_file_info 隔离、get_files_by_app 隔离")
    print(f"     - SessionService: get_session 隔离、get_sessions_by_app 隔离")
    print(f"     - SessionService: get_session_files_content 隔离")
    print(f"     - MemoryService: save_memory + get_recent_memories 隔离")
    print(f"     - 联动: append_chat_message + get_full_context 隔离")
    print(f"     - 兼容性: 不传 app_id 时的行为")
    print(f"     - 边界: 不存在的 app、重复保存幂等性")
    print(f"     - 数据清理验证")

    sys.exit(0 if failed == 0 else 1)
