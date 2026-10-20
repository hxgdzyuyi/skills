from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import KeywordData, Market, normalize


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def digest(identity: dict) -> str:
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def request_identity(
    keyword: str, market: Market, endpoint: str, devices: list[str], namespace: str = "production"
) -> dict:
    return {
        "provider": "DataForSEO",
        "api_origin": "https://api.dataforseo.com",
        "endpoint": endpoint,
        "keyword": normalize(keyword),
        "location_code": market.location_code,
        "language_code": market.language_code,
        "engine": market.engine,
        "period": "monthly",
        "devices": sorted(devices),
        "date_from": None,
        "date_to": None,
        "window": "provider-default-24-months",
        "normalizer": "nfkc-space-lower-v1",
        "namespace": namespace,
    }


class Cache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        with self.connect() as db:
            db.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS keyword_cache (
                key TEXT PRIMARY KEY, identity TEXT NOT NULL, value TEXT NOT NULL,
                fetched_at TEXT NOT NULL, expires_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY, value TEXT NOT NULL, fetched_at TEXT NOT NULL,
                expires_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS request_ledger (
                key TEXT PRIMARY KEY, attempted_at TEXT NOT NULL, cost_usd REAL,
                outcome TEXT NOT NULL);
            """)
        path.chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def get(self, identity: dict, now: datetime | None = None) -> KeywordData | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT value, expires_at FROM keyword_cache WHERE key=?", (digest(identity),)
            ).fetchone()
        if not row:
            return None
        data = KeywordData.model_validate_json(row[0])
        data.cache_hit = True
        if datetime.fromisoformat(row[1]) <= (now or utcnow()):
            data.status = "stale"
            data.reason = "缓存已过期且尚未刷新；历史数值仅供查看，不参与评分"
        return data

    def put(self, identity: dict, data: KeywordData, ttl: int):
        if data.status not in {"ok", "zero", "no_data"}:
            return  # Network errors and unsupported combinations never masquerade as zero.
        data.fetched_at = data.fetched_at or utcnow()
        data.expires_at = data.fetched_at + timedelta(seconds=ttl)
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO keyword_cache VALUES (?,?,?,?,?)",
                (
                    digest(identity),
                    json.dumps(identity, sort_keys=True),
                    data.model_dump_json(),
                    data.fetched_at.isoformat(),
                    data.expires_at.isoformat(),
                ),
            )

    def get_metadata(
        self, key: str, now: datetime | None = None
    ) -> tuple[dict | list, datetime] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT value, fetched_at, expires_at FROM metadata WHERE key=?", (key,)
            ).fetchone()
        if not row or datetime.fromisoformat(row[2]) <= (now or utcnow()):
            return None
        return json.loads(row[0]), datetime.fromisoformat(row[1])

    def put_metadata(self, key: str, value: dict | list, ttl: int) -> datetime:
        now = utcnow()
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO metadata VALUES (?,?,?,?)",
                (
                    key,
                    json.dumps(value),
                    now.isoformat(),
                    (now + timedelta(seconds=ttl)).isoformat(),
                ),
            )
        return now

    def reserve(self, batch: dict, cooldown: int) -> bool:
        now = utcnow()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT attempted_at FROM request_ledger WHERE key=?", (digest(batch),)
            ).fetchone()
            if row and datetime.fromisoformat(row[0]) + timedelta(seconds=cooldown) > now:
                return False
            db.execute(
                "INSERT OR REPLACE INTO request_ledger VALUES (?,?,?,?)",
                (digest(batch), now.isoformat(), None, "submitted_cost_unknown"),
            )
        return True

    def finish(self, batch: dict, cost: float | None, outcome: str):
        with self.connect() as db:
            db.execute(
                "UPDATE request_ledger SET cost_usd=?, outcome=? WHERE key=?",
                (cost, outcome, digest(batch)),
            )
