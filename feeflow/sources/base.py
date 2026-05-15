"""Data source adapter interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class Record(dict):
    """A data record from any source.

    Expected keys:
        name (str): The entity name to match
        id (str, optional): Unique identifier
        attributes (dict, optional): Additional fields
        source (str, optional): Origin identifier
    """

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


class DataSource(ABC):
    """Interface for all data source adapters.

    Implementations read data from various sources and return
    lists of ``Record`` objects.  Column mapping is config-driven,
    so no field names are hardcoded.
    """

    name: str = "unnamed"

    @abstractmethod
    def read(self, config: dict) -> list[Record]:
        """Read records from the configured source.

        Args:
            config: Adapter-specific configuration dict.

        Returns:
            List of Record objects.
        """

    def validate_config(self, config: dict) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors: list[str] = []
        return errors

    def resolve_columns(
        self, row: dict, column_mapping: dict, row_index: int
    ) -> Optional[Record]:
        """Build a Record from a raw row dict using column mapping.

        ``column_mapping`` keys: ``name``, ``id``, ``attributes`` (sub-dict).
        Values are column names or pipe-separated alternatives.
        """
        name_col = column_mapping.get("name", "")
        id_col = column_mapping.get("id", "")
        attr_map = column_mapping.get("attributes", {})

        name = self._pick_column(row, name_col)
        if not name:
            return None

        record = Record(name=name.strip())
        record.source = self.name

        if id_col:
            raw_id = self._pick_column(row, id_col)
            if raw_id:
                record.id = str(raw_id).strip()

        attrs: dict = {}
        for attr_key, col_expr in attr_map.items():
            val = self._pick_column(row, col_expr)
            if val is not None:
                attrs[attr_key] = str(val).strip() if isinstance(val, str) else val
        if attrs:
            record.attributes = attrs

        return record

    @staticmethod
    def _pick_column(row: dict, expression: str) -> Any:
        """Pick a value from row using a column expression.

        Supports pipe-separated alternatives: "客户名称|机构名称" means
        try "客户名称" first, then "机构名称".
        """
        for col in expression.split("|"):
            col = col.strip()
            if col and col in row:
                val = row[col]
                if val is not None and str(val).strip():
                    return val
        return None
