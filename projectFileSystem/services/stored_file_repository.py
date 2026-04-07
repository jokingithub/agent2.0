from __future__ import annotations

import importlib
import json
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from Schema import StoredFile
from utils.errors import ConfigStoreError


class PgStoredFileRepository:
    """PostgreSQL 文件结果仓储。"""

    def __init__(self, dsn: str | None = None) -> None:
        if dsn:
            self.dsn = dsn
        elif os.getenv("PG_URI", ""):
            self.dsn = os.getenv("PG_URI", "")
        else:
            self.dsn = os.getenv("PG_DSN", "")

        if not self.dsn:
            raise ConfigStoreError("缺少 PG_URI/PG_DSN 配置")

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
        CREATE TABLE IF NOT EXISTS project_files (
            file_id VARCHAR(64) NOT NULL,
            project_id VARCHAR(64) NOT NULL,
            original_name TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            content TEXT NOT NULL,
            elements JSONB NOT NULL,
            upload_time TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (project_id, file_id)
        );

        CREATE INDEX IF NOT EXISTS idx_project_files_project_time
        ON project_files (project_id, upload_time DESC);
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)

    def add_file(self, project_id: str, item: StoredFile) -> None:
        sql = """
        INSERT INTO project_files (
            file_id, project_id, original_name, stored_path,
            file_type, content, elements, upload_time
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (project_id, file_id) DO UPDATE
        SET original_name = EXCLUDED.original_name,
            stored_path = EXCLUDED.stored_path,
            file_type = EXCLUDED.file_type,
            content = EXCLUDED.content,
            elements = EXCLUDED.elements,
            upload_time = EXCLUDED.upload_time;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        item.file_id,
                        project_id,
                        item.original_name,
                        item.stored_path,
                        item.file_type,
                        item.content,
                        json.dumps(item.elements, ensure_ascii=False),
                        item.upload_time,
                    ),
                )

    def list_files(self, project_id: str) -> list[StoredFile]:
        sql = """
        SELECT
            file_id,
            project_id,
            original_name,
            stored_path,
            file_type,
            content,
            elements,
            upload_time
        FROM project_files
        WHERE project_id = %s
        ORDER BY upload_time DESC;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (project_id,))
                rows = cur.fetchall()

        return [
            StoredFile(
                file_id=row[0],
                project_id=row[1],
                original_name=row[2],
                stored_path=row[3],
                file_type=row[4],
                content=row[5],
                elements=row[6] or {},
                upload_time=row[7] if isinstance(row[7], datetime) else datetime.now(),
            )
            for row in rows
        ]

    def delete_project(self, project_id: str) -> bool:
        sql = "DELETE FROM project_files WHERE project_id = %s;"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (project_id,))
                return cur.rowcount > 0

    def get_by_file_id(self, file_id: str) -> StoredFile | None:
        sql = """
        SELECT
            file_id,
            project_id,
            original_name,
            stored_path,
            file_type,
            content,
            elements,
            upload_time
        FROM project_files
        WHERE file_id = %s
        ORDER BY upload_time DESC
        LIMIT 1;
        """
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (file_id,))
                row = cur.fetchone()

        if not row:
            return None

        return StoredFile(
            file_id=row[0],
            project_id=row[1],
            original_name=row[2],
            stored_path=row[3],
            file_type=row[4],
            content=row[5],
            elements=row[6] or {},
            upload_time=row[7] if isinstance(row[7], datetime) else datetime.now(),
        )
