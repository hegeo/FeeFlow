"""SQL database data source adapter."""

from __future__ import annotations

import logging
from typing import Any

from feeflow.sources.base import DataSource, Record

logger = logging.getLogger(__name__)


class SQLDatabaseSource(DataSource):
    """Reads records from a SQL database.

    Config options::

        connection: str               # SQLAlchemy connection string
        query: str                    # SQL query
        column_mapping: dict          # {name, id, attributes: {...}}
    """

    name = "sql"

    def read(self, config: dict) -> list[Record]:
        conn_str = config.get("connection", "")
        query = config.get("query", "")
        mapping = config.get("column_mapping", {})

        if not conn_str or not query:
            logger.error("SQL source missing connection or query")
            return []

        rows = self._execute_query(conn_str, query)
        records: list[Record] = []

        for i, row in enumerate(rows, start=1):
            rec = self.resolve_columns(row, mapping, i)
            if rec:
                records.append(rec)

        return records

    def validate_config(self, config: dict) -> list[str]:
        errors: list[str] = []
        if "connection" not in config:
            errors.append("Missing required config: connection")
        if "query" not in config:
            errors.append("Missing required config: query")
        return errors

    def _execute_query(self, conn_str: str, query: str) -> list[dict]:
        """Execute SQL query and return list of dicts."""
        try:
            from sqlalchemy import create_engine, text
        except ImportError:
            logger.error("sqlalchemy is required for SQLDatabaseSource")
            return []

        try:
            engine = create_engine(conn_str)
            with engine.connect() as conn:
                result = conn.execute(text(query))
                rows = [dict(row._mapping) for row in result]
            return rows
        except Exception as e:
            logger.error("SQL query failed: %s", e)
            return []
