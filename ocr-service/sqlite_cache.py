import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional
import numpy as np  # 新增导入

# 新增：用于处理 NumPy 数据的自定义编码器
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        # 处理 NumPy 数组
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        # 处理 NumPy 标量 (int64, float32 等)
        if isinstance(obj, np.generic):
            return obj.item()
        # 尝试处理带有 __dict__ 的对象（有些类可以转为字典）
        # 或者直接转为字符串，防止报错
        try:
            return super(NumpyEncoder, self).default(obj)
        except TypeError:
            return str(obj) # 最后的保底方案：转为字符串，如 "<Font object...>"

class SQLiteTTLCache:
    def __init__(self, db_path: str, default_ttl_seconds: int = 3600, enabled: bool = True):
        self.db_path = db_path
        self.default_ttl_seconds = max(1, int(default_ttl_seconds))
        self.enabled = enabled
        self._lock = threading.RLock()

        if self.enabled:
            self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with self._lock, self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ocr_cache (
                    cache_key TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ocr_cache_expires_at ON ocr_cache(expires_at)"
            )
            conn.commit()

    def get(self, cache_key: str) -> Optional[Any]:
        if not self.enabled:
            return None

        now = int(time.time())
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT response_json, expires_at FROM ocr_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()

            if not row:
                return None

            response_json, expires_at = row
            if expires_at <= now:
                conn.execute("DELETE FROM ocr_cache WHERE cache_key = ?", (cache_key,))
                conn.commit()
                return None

            return json.loads(response_json)

    def set(self, cache_key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        if not self.enabled:
            return

        now = int(time.time())
        ttl = self.default_ttl_seconds if ttl_seconds is None else max(1, int(ttl_seconds))
        expires_at = now + ttl
        
        # 修改点：添加 cls=NumpyEncoder 以支持 ndarray 序列化
        response_json = json.dumps(value, ensure_ascii=False, cls=NumpyEncoder)

        with self._lock, self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO ocr_cache(cache_key, response_json, created_at, expires_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (cache_key, response_json, now, expires_at),
            )
            conn.execute("DELETE FROM ocr_cache WHERE expires_at <= ?", (now,))
            conn.commit()