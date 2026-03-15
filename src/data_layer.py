"""
src/data_layer.py
SQLite-backed Chainlit data layer.
Compatible with Chainlit 1.0.200 — imports PageInfo/PaginatedResponse
from literalai (which is a dependency of chainlit 1.0.200).
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from chainlit.data import BaseDataLayer
from chainlit.types import Feedback, Pagination, ThreadDict, ThreadFilter
from chainlit.user import PersistedUser, User
from literalai import PageInfo, PaginatedResponse

DB_PATH = "zomato_chat.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    identifier  TEXT UNIQUE NOT NULL,
    metadata    TEXT DEFAULT '{}',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS threads (
    id          TEXT PRIMARY KEY,
    name        TEXT,
    user_id     TEXT,
    metadata    TEXT DEFAULT '{}',
    tags        TEXT DEFAULT '[]',
    created_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS steps (
    id          TEXT PRIMARY KEY,
    thread_id   TEXT NOT NULL,
    type        TEXT NOT NULL,
    name        TEXT,
    output      TEXT,
    metadata    TEXT DEFAULT '{}',
    created_at  TEXT NOT NULL,
    start_time  TEXT,
    end_time    TEXT,
    parent_id   TEXT,
    FOREIGN KEY (thread_id) REFERENCES threads(id)
);
CREATE TABLE IF NOT EXISTS elements (
    id          TEXT PRIMARY KEY,
    thread_id   TEXT,
    type        TEXT,
    name        TEXT,
    url         TEXT,
    mime        TEXT,
    metadata    TEXT DEFAULT '{}',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedbacks (
    id          TEXT PRIMARY KEY,
    step_id     TEXT,
    value       INTEGER,
    comment     TEXT,
    created_at  TEXT NOT NULL
);
"""


class SQLiteDataLayer(BaseDataLayer):

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Users ─────────────────────────────────────────────────────────────

    async def get_user(self, identifier: str) -> Optional[PersistedUser]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE identifier = ?", (identifier,)
            ).fetchone()
        if row:
            return PersistedUser(
                id=row["id"],
                identifier=row["identifier"],
                metadata=json.loads(row["metadata"]),
                createdAt=row["created_at"],
            )
        return None

    async def create_user(self, user: User) -> Optional[PersistedUser]:
        uid = str(uuid.uuid4())
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (id, identifier, metadata, created_at) "
                "VALUES (?, ?, ?, ?)",
                (uid, user.identifier, json.dumps(user.metadata or {}), now),
            )
            conn.commit()
        return await self.get_user(user.identifier)

    # ── Feedback ──────────────────────────────────────────────────────────

    async def upsert_feedback(self, feedback: Feedback) -> str:
        fid = getattr(feedback, "id", None) or str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO feedbacks "
                "(id, step_id, value, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                (fid, feedback.forId, feedback.value,
                 getattr(feedback, "comment", None), self._now()),
            )
            conn.commit()
        return fid

    async def delete_feedback(self, feedback_id: str) -> bool:
        with self._conn() as conn:
            conn.execute("DELETE FROM feedbacks WHERE id = ?", (feedback_id,))
            conn.commit()
        return True

    # ── Elements ──────────────────────────────────────────────────────────

    async def create_element(self, element) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO elements "
                "(id, thread_id, type, name, url, mime, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    element.id,
                    getattr(element, "thread_id", None),
                    getattr(element, "type", None),
                    element.name,
                    getattr(element, "url", None),
                    getattr(element, "mime", None),
                    "{}",
                    self._now(),
                ),
            )
            conn.commit()

    async def get_element(self, thread_id: str, element_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM elements WHERE thread_id = ? AND id = ?",
                (thread_id, element_id),
            ).fetchone()
        return dict(row) if row else None

    async def delete_element(self, element_id: str, thread_id: Optional[str] = None) -> bool:
        with self._conn() as conn:
            conn.execute("DELETE FROM elements WHERE id = ?", (element_id,))
            conn.commit()
        return True

    # ── Steps ─────────────────────────────────────────────────────────────

    async def create_step(self, step_dict: Dict) -> None:
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO steps "
                "(id, thread_id, type, name, output, metadata, "
                " created_at, start_time, end_time, parent_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    step_dict.get("id", str(uuid.uuid4())),
                    step_dict.get("threadId", ""),
                    step_dict.get("type", ""),
                    step_dict.get("name", ""),
                    step_dict.get("output", ""),
                    json.dumps(step_dict.get("metadata", {})),
                    step_dict.get("createdAt", now),
                    step_dict.get("start", now),
                    step_dict.get("end", now),
                    step_dict.get("parentId"),
                ),
            )
            conn.commit()

    async def update_step(self, step_dict: Dict) -> None:
        await self.create_step(step_dict)

    async def delete_step(self, step_id: str) -> bool:
        with self._conn() as conn:
            conn.execute("DELETE FROM steps WHERE id = ?", (step_id,))
            conn.commit()
        return True

    # ── Threads ───────────────────────────────────────────────────────────

    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        with self._conn() as conn:
            t = conn.execute(
                "SELECT * FROM threads WHERE id = ?", (thread_id,)
            ).fetchone()
            if not t:
                return None
            steps = conn.execute(
                "SELECT * FROM steps WHERE thread_id = ? ORDER BY created_at ASC",
                (thread_id,),
            ).fetchall()
            elements = conn.execute(
                "SELECT * FROM elements WHERE thread_id = ?", (thread_id,)
            ).fetchall()
            user_identifier: Optional[str] = None
            if t["user_id"]:
                u = conn.execute(
                    "SELECT identifier FROM users WHERE id = ?", (t["user_id"],)
                ).fetchone()
                if u:
                    user_identifier = u["identifier"]

        return ThreadDict(
            id=t["id"],
            createdAt=t["created_at"],
            name=t["name"],
            userId=t["user_id"],
            userIdentifier=user_identifier,
            tags=json.loads(t["tags"] or "[]"),
            metadata=json.loads(t["metadata"] or "{}"),
            steps=[
                {
                    "id": s["id"],
                    "threadId": s["thread_id"],
                    "type": s["type"],
                    "name": s["name"],
                    "output": s["output"],
                    "metadata": json.loads(s["metadata"] or "{}"),
                    "createdAt": s["created_at"],
                    "start": s["start_time"],
                    "end": s["end_time"],
                    "parentId": s["parent_id"],
                }
                for s in steps
            ],
            elements=[
                {
                    "id": e["id"],
                    "threadId": e["thread_id"],
                    "type": e["type"],
                    "name": e["name"],
                    "url": e["url"],
                    "mime": e["mime"],
                }
                for e in elements
            ],
        )

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO threads "
                "(id, name, user_id, metadata, tags, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (thread_id, name, user_id,
                 json.dumps(metadata or {}), json.dumps(tags or []), now),
            )
            if name is not None:
                conn.execute(
                    "UPDATE threads SET name = ? WHERE id = ?", (name, thread_id)
                )
            if user_id is not None:
                conn.execute(
                    "UPDATE threads SET user_id = ? WHERE id = ?", (user_id, thread_id)
                )
            if metadata is not None:
                conn.execute(
                    "UPDATE threads SET metadata = ? WHERE id = ?",
                    (json.dumps(metadata), thread_id),
                )
            if tags is not None:
                conn.execute(
                    "UPDATE threads SET tags = ? WHERE id = ?",
                    (json.dumps(tags), thread_id),
                )
            conn.commit()

    async def delete_thread(self, thread_id: str) -> bool:
        with self._conn() as conn:
            conn.execute("DELETE FROM steps WHERE thread_id = ?", (thread_id,))
            conn.execute("DELETE FROM elements WHERE thread_id = ?", (thread_id,))
            conn.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
            conn.commit()
        return True

    async def list_threads(
        self,
        pagination: Pagination,
        filters: ThreadFilter,
    ) -> "PaginatedResponse[ThreadDict]":
        conditions: List[str] = []
        params: List = []

        if getattr(filters, "userId", None):
            conditions.append("user_id = ?")
            params.append(filters.userId)
        if getattr(filters, "search", None):
            conditions.append("name LIKE ?")
            params.append(f"%{filters.search}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit = pagination.first or 20
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM threads {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()

        threads: List[ThreadDict] = []
        for row in rows:
            td = await self.get_thread(row["id"])
            if td:
                threads.append(td)

        return PaginatedResponse(
            data=threads,
            pageInfo=PageInfo(
                hasNextPage=len(rows) == limit,
                startCursor=threads[0]["id"] if threads else None,
                endCursor=threads[-1]["id"] if threads else None,
            ),
        )

    async def get_thread_author(self, thread_id: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT u.identifier FROM threads t "
                "LEFT JOIN users u ON t.user_id = u.id "
                "WHERE t.id = ?",
                (thread_id,),
            ).fetchone()
        return row["identifier"] if row and row["identifier"] else None