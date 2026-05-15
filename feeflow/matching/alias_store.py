"""SQLite-based persistent alias store — domain-agnostic name mapping."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


class AliasStore:
    """Persistent alias store backed by SQLite.

    Stores (canonical_name, alias_pattern) mappings for manual
    overrides of the matching engine.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path("alias_store.db")
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT NOT NULL,
                alias_pattern TEXT NOT NULL,
                match_type TEXT NOT NULL DEFAULT 'exact',
                confidence REAL NOT NULL DEFAULT 100.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(canonical_name, alias_pattern)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alias_pattern ON aliases(alias_pattern)"
        )
        conn.commit()

    def add_alias(
        self,
        canonical_name: str,
        alias_pattern: str,
        match_type: str = "exact",
        confidence: float = 100.0,
    ) -> None:
        """Insert or replace an alias mapping."""
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO aliases
                (canonical_name, alias_pattern, match_type, confidence)
            VALUES (?, ?, ?, ?)
            """,
            (canonical_name, alias_pattern, match_type, confidence),
        )
        conn.commit()

    def lookup(self, name: str) -> Optional[str]:
        """Look up a name in the alias store.

        Returns the canonical name if found, else None.
        """
        conn = self._get_conn()

        # Exact match first
        row = conn.execute(
            "SELECT canonical_name FROM aliases WHERE alias_pattern = ? AND match_type = 'exact'",
            (name,),
        ).fetchone()
        if row:
            return row["canonical_name"]

        # LIKE match: check if name contains any like-pattern
        for row in conn.execute(
            "SELECT alias_pattern, canonical_name FROM aliases WHERE match_type = 'like'"
        ).fetchall():
            pattern = row["alias_pattern"].replace("%", "")
            if pattern and pattern in name:
                return row["canonical_name"]

        return None

    def get_all_aliases(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT canonical_name, alias_pattern, match_type, confidence FROM aliases ORDER BY canonical_name"
        ).fetchall()
        return [dict(r) for r in rows]

    def remove_alias(self, canonical_name: str, alias_pattern: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM aliases WHERE canonical_name = ? AND alias_pattern = ?",
            (canonical_name, alias_pattern),
        )
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
