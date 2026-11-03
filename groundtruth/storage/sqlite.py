from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from groundtruth.models.report import EvidenceBundle
from groundtruth.storage.repository import StoredInvestigation
from groundtruth.utils.redaction import SENSITIVE_KEY_PATTERN

SCHEMA = """
CREATE TABLE IF NOT EXISTS investigations (
    investigation_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    mode TEXT NOT NULL,
    fixture INTEGER NOT NULL,
    resource_name TEXT NOT NULL,
    resource_arn TEXT,
    status TEXT NOT NULL,
    confidence TEXT NOT NULL,
    recommendation_code TEXT NOT NULL,
    checksum TEXT,
    report_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_investigations_created_at ON investigations(created_at DESC);
CREATE TABLE IF NOT EXISTS ui_preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class SqliteInvestigationRepository:
    def __init__(self, database_url: str = "sqlite:///./groundtruth.db") -> None:
        self.database_url = database_url
        self._lock = threading.RLock()
        self._memory_connection: sqlite3.Connection | None = None
        self._path = self._resolve_path(database_url)
        if self._path is None:
            self._memory_connection = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_connection.row_factory = sqlite3.Row
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @staticmethod
    def _resolve_path(database_url: str) -> Path | None:
        if database_url in {"sqlite://", "sqlite:///:memory:", ":memory:"}:
            return None
        prefix = "sqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("Only sqlite:/// database URLs are supported in the MVP.")
        raw = database_url[len(prefix) :]
        if not raw or raw == ":memory:":
            return None
        return Path(raw).expanduser()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self._memory_connection is not None:
                yield self._memory_connection
                return
            assert self._path is not None
            connection = sqlite3.connect(self._path, timeout=10.0)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("PRAGMA journal_mode = WAL")
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(SCHEMA)

    def save(self, bundle: EvidenceBundle) -> StoredInvestigation:
        payload = bundle.model_dump(mode="json")
        report_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        checksum = bundle.integrity.checksum if bundle.integrity else None
        created_at = bundle.exported_at.isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO investigations (
                    investigation_id, created_at, mode, fixture, resource_name, resource_arn,
                    status, confidence, recommendation_code, checksum, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle.investigation_id,
                    created_at,
                    bundle.mode,
                    1 if bundle.fixture else 0,
                    bundle.resource.name,
                    bundle.resource.arn,
                    bundle.status,
                    bundle.confidence,
                    str((bundle.recommendation or {}).get("code", "")),
                    checksum,
                    report_json,
                ),
            )
        return StoredInvestigation(
            investigation_id=bundle.investigation_id,
            created_at=bundle.exported_at,
            mode=bundle.mode,
            fixture=bundle.fixture,
            resource_name=bundle.resource.name,
            resource_arn=bundle.resource.arn,
            status=bundle.status,
            confidence=bundle.confidence,
            recommendation_code=str((bundle.recommendation or {}).get("code", "")),
            checksum=checksum,
            report=payload,
        )

    def get(self, investigation_id: str) -> StoredInvestigation | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM investigations WHERE investigation_id = ?",
                (investigation_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row, include_report=True)

    def list(self, limit: int = 50) -> list[StoredInvestigation]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT investigation_id, created_at, mode, fixture, resource_name, resource_arn,
                       status, confidence, recommendation_code, checksum, NULL AS report_json
                FROM investigations
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._row_to_record(row, include_report=False) for row in rows]

    def delete(self, investigation_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM investigations WHERE investigation_id = ?",
                (investigation_id,),
            )
        return cursor.rowcount > 0

    def count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM investigations").fetchone()
        return int(row["total"] if row else 0)

    def set_preference(self, key: str, value: str) -> None:
        if SENSITIVE_KEY_PATTERN.search(key):
            raise ValueError("Secret-like preference keys are not persisted.")
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO ui_preferences (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, datetime.now(timezone.utc).isoformat()),
            )

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        with self._connection() as connection:
            row = connection.execute("SELECT value FROM ui_preferences WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    @staticmethod
    def _row_to_record(row: sqlite3.Row, *, include_report: bool) -> StoredInvestigation:
        report: dict[str, Any] = {}
        if include_report and row["report_json"]:
            report = json.loads(row["report_json"])
        return StoredInvestigation(
            investigation_id=str(row["investigation_id"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            mode=str(row["mode"]),
            fixture=bool(row["fixture"]),
            resource_name=str(row["resource_name"]),
            resource_arn=str(row["resource_arn"]) if row["resource_arn"] else None,
            status=str(row["status"]),
            confidence=str(row["confidence"]),
            recommendation_code=str(row["recommendation_code"]),
            checksum=str(row["checksum"]) if row["checksum"] else None,
            report=report,
        )
