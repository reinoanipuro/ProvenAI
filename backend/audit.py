"""SQLite storage for inspection results and a step-by-step audit log."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .schemas import Inspection

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inspections (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    document TEXT NOT NULL,
    overall TEXT NOT NULL,
    result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    inspection_id TEXT NOT NULL,
    event TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


class AuditStore:
    def __init__(self, path: Path):
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self._path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def log(self, inspection_id: str, event: str, payload: dict) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO audit_log (ts, inspection_id, event, payload) VALUES (?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    inspection_id,
                    event,
                    json.dumps(payload, sort_keys=True, ensure_ascii=False),
                ),
            )

    def save_inspection(self, inspection: Inspection) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO inspections (id, created_at, document, overall, result_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (inspection.id, inspection.created_at, inspection.document,
                 inspection.overall, inspection.model_dump_json()),
            )

    def events(self, inspection_id: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT seq, ts, event, payload FROM audit_log "
                "WHERE inspection_id = ? ORDER BY seq",
                (inspection_id,),
            ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]
