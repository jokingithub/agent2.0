from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit

from config import DEFAULT_LLM_CONFIG, DEFAULT_OCR_CONFIG
from utils.errors import ConfigStoreError
from utils.logging import get_logger


class PgProjectConfigRepository:
    """PostgreSQL 项目配置仓储。"""

    def __init__(self, dsn: str | None = None) -> None:
        self.logger = get_logger(__name__)
        source = "explicit"
        if dsn:
            self.dsn = dsn
        elif os.getenv("PG_URI", ""):
            self.dsn = os.getenv("PG_URI", "")
            source = "PG_URI"
        else:
            self.dsn = os.getenv("PG_DSN", "")
            source = "PG_DSN"

        if not self.dsn:
            raise ConfigStoreError("缺少 PG_URI/PG_DSN 配置")

        self.logger.info("PostgreSQL 配置仓储已初始化: source=%s dsn=%s", source, self._mask_dsn(self.dsn))

    def _mask_dsn(self, dsn: str) -> str:
        parts = urlsplit(dsn)
        if not parts.scheme or not parts.netloc:
            return "***"

        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        user = parts.username or ""
        safe_user = f"{user}:***@" if user else ""
        safe_netloc = f"{safe_user}{host}{port}"
        return urlunsplit((parts.scheme, safe_netloc, parts.path, parts.query, parts.fragment))

    @contextmanager
    def _conn(self) -> Iterator[Any]:
        try:
            psycopg = importlib.import_module("psycopg")
        except Exception as exc:
            raise ConfigStoreError("缺少依赖 psycopg，请先安装") from exc

        conn = psycopg.connect(self.dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        sql = """
        CREATE TABLE IF NOT EXISTS project_configs (
            project_id VARCHAR(64) PRIMARY KEY,
            need_files JSONB NOT NULL,
            ocr JSONB NOT NULL,
            llm JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)

    def upsert_project(
        self,
        project_id: str,
        need_files: list[dict[str, Any]],
        ocr: dict[str, Any] | None,
        llm: dict[str, Any] | None,
    ) -> None:
        sql = """
        INSERT INTO project_configs (project_id, need_files, ocr, llm, updated_at)
        VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, NOW())
        ON CONFLICT (project_id) DO UPDATE
        SET need_files = EXCLUDED.need_files,
            ocr = EXCLUDED.ocr,
            llm = EXCLUDED.llm,
            updated_at = NOW();
        """
        import json

        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        project_id,
                        json.dumps(need_files, ensure_ascii=False),
                        json.dumps(ocr or DEFAULT_OCR_CONFIG, ensure_ascii=False),
                        json.dumps(llm or DEFAULT_LLM_CONFIG, ensure_ascii=False),
                    ),
                )

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        sql = """
        SELECT project_id, need_files, ocr, llm
        FROM project_configs
        WHERE project_id = %s;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (project_id,))
                row = cur.fetchone()

        if not row:
            return None

        return {
            "project_id": row[0],
            "need_files": row[1],
            "ocr": row[2],
            "llm": row[3],
        }

    def list_project_ids(self) -> list[str]:
        sql = "SELECT project_id FROM project_configs ORDER BY created_at DESC;"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [r[0] for r in rows]

    def delete_project(self, project_id: str) -> bool:
        sql = "DELETE FROM project_configs WHERE project_id = %s;"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (project_id,))
                return cur.rowcount > 0
