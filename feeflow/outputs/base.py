"""Output adapter interface — for report generation and action execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OutputAdapter(ABC):
    """Interface for writing results and executing automation actions."""

    name: str = "unnamed"

    @abstractmethod
    def write(self, data: list[dict], schema: dict, config: dict) -> str:
        """Write data to output.

        Args:
            data: List of row dicts.
            schema: Column definitions.
            config: Adapter-specific options.

        Returns:
            Path or identifier of the written output.
        """

    def execute_action(self, action: dict, context: dict) -> dict:
        """Execute an automation action (send msg, quit group, etc.).

        Args:
            action: Action definition dict.
            context: Workflow context (registry, platform adapters, etc.).

        Returns:
            Result dict with status and details.
        """
        return {"status": "not_implemented"}

    def validate_config(self, config: dict) -> list[str]:
        return []

    @staticmethod
    def resolve_column(row: dict, key: str) -> Any:
        """Resolve a dot-separated key from a row dict.

        Supports nested access: ``attributes.sales`` → row["attributes"]["sales"]
        Also supports computed keys like ``best_group.display``.
        """
        parts = key.split(".")
        val: Any = row
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part, "")
            elif isinstance(val, list) and part.isdigit():
                idx = int(part)
                val = val[idx] if idx < len(val) else ""
            elif isinstance(val, list) and "_" in part:
                # e.g. groups[0].display → first group's display
                pass
            else:
                return ""
        return val if val is not None else ""
