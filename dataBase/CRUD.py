# -*- coding: utf-8 -*-
import uuid
import json
from typing import List, Dict, Any, Optional
from sqlalchemy import text


class CRUD:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def _get_session(self):
        return self.session_factory()

    def insert_document(self, collection_name: str, document: Dict) -> str:
        doc_id = document.pop("_id", None)
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        doc_id = str(doc_id)

        with self._get_session() as session:
            session.execute(
                text(f"INSERT INTO {collection_name} (id, data) VALUES (:id, :data)"),
                {"id": doc_id, "data": json.dumps(document, default=str)}
            )
            session.commit()
        return doc_id

    def find_one(self, collection_name: str, query: Dict) -> Optional[Dict]:
        where_clause, params = self._build_where(query)

        with self._get_session() as session:
            result = session.execute(
                text(f"SELECT id, data FROM {collection_name} WHERE {where_clause} LIMIT 1"),
                params
            ).fetchone()

        if result is None:
            return None
        return self._row_to_doc(result)


    def find_documents(
        self,
        collection_name: str,
        query: Dict,
        sort_by: str = None,
        ascending: bool = True,
        limit: int = 0,
        sort_as_number: bool = False
    ) -> List[Dict]:
        where_clause, params = self._build_where(query)

        sql = f"SELECT id, data FROM {collection_name} WHERE {where_clause}"

        if sort_by:
            direction = "ASC" if ascending else "DESC"
            if sort_as_number:
                sql += f" ORDER BY (data->>'{sort_by}')::numeric {direction}"
            else:
                sql += f" ORDER BY data->>'{sort_by}' {direction}"

        if limit > 0:
            sql += f" LIMIT {limit}"

        with self._get_session() as session:
            rows = session.execute(text(sql), params).fetchall()

        return [self._row_to_doc(row) for row in rows]


    def update_document(self, collection_name: str, query: Dict, update_data: Dict, upsert: bool = False) -> int:
        if "_id" in update_data:
            update_data.pop("_id")

        where_clause, params = self._build_where(query)
        params["update_data"] = json.dumps(update_data, default=str)

        # 用 CAST 替代 ::jsonb，避免和 SQLAlchemy 的 :param 冲突
        update_sql = f"UPDATE {collection_name} SET data = data || CAST(:update_data AS jsonb) WHERE {where_clause}"

        with self._get_session() as session:
            if upsert:
                result = session.execute(text(update_sql), params)
                if result.rowcount == 0:
                    doc_id = query.get("_id", str(uuid.uuid4()))
                    merged = {**query, **update_data}
                    merged.pop("_id", None)
                    session.execute(
                        text(f"INSERT INTO {collection_name} (id, data) VALUES (:id, CAST(:data AS jsonb))"),
                        {"id": str(doc_id), "data": json.dumps(merged, default=str)}
                    )
                count = max(result.rowcount, 1)
            else:
                result = session.execute(text(update_sql), params)
                count = result.rowcount
            session.commit()
        return count


    def delete_document(self, collection_name: str, query: Dict) -> int:
        where_clause, params = self._build_where(query)

        with self._get_session() as session:
            result = session.execute(
                text(f"DELETE FROM {collection_name} WHERE {where_clause}"),
                params
            )
            session.commit()
        return result.rowcount

    #----内部工具方法 ----
    def _build_where(self, query: Dict) -> tuple:
        if not query:
            return "1=1", {}

        conditions = []
        params = {}

        for i, (key, value) in enumerate(query.items()):
            param_name = f"p{i}"

            if key == "_id":
                if isinstance(value, dict) and "$in" in value:
                    # _id + $in → 查 id 列
                    in_values = value["$in"]
                    placeholders = []
                    for j, v in enumerate(in_values):
                        ph = f"{param_name}_{j}"
                        placeholders.append(f":{ph}")
                        params[ph] = str(v)
                    conditions.append(f"id IN ({', '.join(placeholders)})")
                else:
                    conditions.append(f"id = :{param_name}")
                    params[param_name] = str(value)
            elif isinstance(value, dict) and "$in" in value:
                in_values = value["$in"]
                placeholders = []
                for j, v in enumerate(in_values):
                    ph = f"{param_name}_{j}"
                    placeholders.append(f":{ph}")
                    params[ph] = str(v)
                conditions.append(f"data->>'{key}' IN ({', '.join(placeholders)})")
            else:
                conditions.append(f"data->>'{key}' = :{param_name}")
                params[param_name] = str(value)

        return " AND ".join(conditions), params


    def _row_to_doc(self, row) -> Dict:
        doc = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        doc["_id"] = row[0]
        return doc
