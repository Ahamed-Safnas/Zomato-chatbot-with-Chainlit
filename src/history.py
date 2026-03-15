"""
src/history.py
Lightweight SQLite chat history.
One simple `chats` table — no complex joins, no over-engineering.
Plugs into Chainlit's BaseDataLayer for the sidebar.
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

DB_PATH = "chat_history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,
    identifier TEXT UNIQUE NOT NULL,
    metadata   TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chats (
    id         TEXT PRIMARY KEY,
    name       TEXT,
    user_id    TEXT,
    steps      TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HistoryDataLayer(BaseDataLayer):
    """
    Minimal data layer — just enough for the sidebar to work.
    Only two tables: users and chats.
    """

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        with self._conn() as c:
            c.executescript(_SCHEMA)
            c.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Users ─────────────────────────────────────────────────────────────

    async def get_user(self, identifier: str) -> Optional[PersistedUser]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM users WHERE identifier=?", (identifier,)
            ).fetchone()
        if not row:
            return None
        return PersistedUser(
            id=row["id"],
            identifier=row["identifier"],
            metadata=json.loads(row["metadata"]),
            createdAt=row["created_at"],
        )

    async def create_user(self, user: User) -> Optional[PersistedUser]:
        uid = str(uuid.uuid4())
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO users VALUES (?,?,?,?)",
                (uid, user.identifier, json.dumps(user.metadata or {}), _now()),
            )
            c.commit()
        return await self.get_user(user.identifier)

    # ── Feedback (no-op — not needed) ─────────────────────────────────────

    async def upsert_feedback(self, feedback: Feedback) -> str:
        return getattr(feedback, "id", str(uuid.uuid4()))

    async def delete_feedback(self, feedback_id: str) -> bool:
        return True

    # ── Elements (no-op — images are URLs, not stored) ────────────────────

    async def create_element(self, element) -> None:
        pass

    async def get_element(self, thread_id: str, element_id: str) -> Optional[Dict]:
        return None

    async def delete_element(self, element_id: str, thread_id: Optional[str] = None) -> bool:
        return True

    # ── Steps — stored as JSON blob inside chats row ──────────────────────

    async def create_step(self, step_dict: Dict) -> None:
        tid = step_dict.get("threadId", "")
        if not tid:
            return
        with self._conn() as c:
            row = c.execute("SELECT steps FROM chats WHERE id=?", (tid,)).fetchone()
            steps = json.loads(row["steps"]) if row else []
            steps.append(step_dict)
            c.execute(
                "INSERT INTO chats(id,name,steps,created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET steps=excluded.steps",
                (tid, step_dict.get("name", "Chat"), json.dumps(steps), _now()),
            )
            c.commit()

    async def update_step(self, step_dict: Dict) -> None:
        await self.create_step(step_dict)

    async def delete_step(self, step_id: str) -> bool:
        return True

    # ── Threads ───────────────────────────────────────────────────────────

    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM chats WHERE id=?", (thread_id,)
            ).fetchone()
        if not row:
            return None
        return ThreadDict(
            id=row["id"],
            createdAt=row["created_at"],
            name=row["name"] or "Chat",
            userId=row["user_id"],
            userIdentifier=None,
            tags=[],
            metadata={},
            steps=json.loads(row["steps"] or "[]"),
            elements=[],
        )

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO chats(id,name,user_id,steps,created_at) "
                "VALUES(?,?,?,'[]',?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "name=COALESCE(excluded.name, name), "
                "user_id=COALESCE(excluded.user_id, user_id)",
                (thread_id, name, user_id, _now()),
            )
            c.commit()

    async def delete_thread(self, thread_id: str) -> bool:
        with self._conn() as c:
            c.execute("DELETE FROM chats WHERE id=?", (thread_id,))
            c.commit()
        return True

    async def get_thread_author(self, thread_id: str) -> Optional[str]:
        return "guest"

    async def list_threads(
        self,
        pagination: Pagination,
        filters: ThreadFilter,
    ) -> "PaginatedResponse[ThreadDict]":
        limit = pagination.first or 20
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM chats ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        threads = [
            ThreadDict(
                id=r["id"],
                createdAt=r["created_at"],
                name=r["name"] or "Chat",
                userId=r["user_id"],
                userIdentifier=None,
                tags=[],
                metadata={},
                steps=json.loads(r["steps"] or "[]"),
                elements=[],
            )
            for r in rows
        ]

        return PaginatedResponse(
            data=threads,
            pageInfo=PageInfo(
                hasNextPage=len(rows) == limit,
                startCursor=threads[0]["id"] if threads else None,
                endCursor=threads[-1]["id"] if threads else None,
            ),
        )
