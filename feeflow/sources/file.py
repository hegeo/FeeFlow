"""File-based data source adapter — reads TXT, CSV, XLSX, YAML, and directory scans."""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from feeflow.sources.base import DataSource, Record

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

logger = logging.getLogger(__name__)


class FileSource(DataSource):
    """Reads data from files: txt, csv, xlsx, yaml, or directory scans.

    Config options::

        path: str                     # File path or directory path
        format: str                   # "xlsx" | "csv" | "txt" | "yaml" | "directory"
        sheet: int | str              # Sheet index/name (xlsx only)
        encoding: str                 # File encoding (default "utf-8")
        column_mapping: dict          # {name, id, attributes: {...}}
        txt_regex: str                # Regex to parse TXT lines
        record_path: str              # YAML key path (e.g. "chatrooms")
        file_patterns: list[str]      # Glob patterns for directory scan
    """

    name = "file"

    def read(self, config: dict) -> list[Record]:
        path = Path(config["path"])
        fmt = config.get("format", self._detect_format(path))

        if fmt == "directory":
            return self._read_directory(path, config)
        elif fmt == "xlsx":
            return self._read_xlsx(path, config)
        elif fmt == "csv":
            return self._read_csv(path, config)
        elif fmt == "txt":
            return self._read_txt(path, config)
        elif fmt == "yaml":
            return self._read_yaml(path, config)
        else:
            raise ValueError(f"Unsupported file format: {fmt}")

    def validate_config(self, config: dict) -> list[str]:
        errors: list[str] = []
        if "path" not in config:
            errors.append("Missing required config: path")
        return errors

    # ── Format detection ────────────────────────────────────────────

    @staticmethod
    def _detect_format(path: Path) -> str:
        suffix = path.suffix.lower()
        return {
            ".xlsx": "xlsx",
            ".xls": "xlsx",  # openpyxl handles .xls partially
            ".csv": "csv",
            ".txt": "txt",
            ".yaml": "yaml",
            ".yml": "yaml",
        }.get(suffix, "txt")

    # ── XLSX reader ─────────────────────────────────────────────────

    def _read_xlsx(self, path: Path, config: dict) -> list[Record]:
        if openpyxl is None:
            raise ImportError("openpyxl is required to read .xlsx files")

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet_name = config.get("sheet", 0)
        if isinstance(sheet_name, int):
            ws = wb.worksheets[sheet_name]
        else:
            ws = wb[sheet_name]

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []

        headers = [str(c).strip() if c else "" for c in rows[0]]
        mapping = config.get("column_mapping", {})

        records: list[Record] = []
        for i, row in enumerate(rows[1:], start=2):
            raw = dict(zip(headers, row))
            rec = self.resolve_columns(raw, mapping, i)
            if rec:
                records.append(rec)

        wb.close()
        return records

    # ── CSV reader ──────────────────────────────────────────────────

    def _read_csv(self, path: Path, config: dict) -> list[Record]:
        encoding = config.get("encoding", "utf-8-sig")
        mapping = config.get("column_mapping", {})

        records: list[Record] = []
        with open(path, encoding=encoding, newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, start=2):
                rec = self.resolve_columns(row, mapping, i)
                if rec:
                    records.append(rec)

        return records

    # ── TXT reader ──────────────────────────────────────────────────

    def _read_txt(self, path: Path, config: dict) -> list[Record]:
        encoding = config.get("encoding", "utf-8")
        regex = config.get("txt_regex", r"(\d{4,6})\s+(\S+)")
        name_keywords = config.get("name_keywords", [])
        pattern = re.compile(regex)

        records: list[Record] = []
        with open(path, encoding=encoding, errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Try regex extraction
                m = pattern.search(line)
                if m:
                    groups = m.groups()
                    name = groups[-1]
                    attrs: dict[str, Any] = {}
                    if len(groups) > 1:
                        attrs["id"] = groups[0]
                    records.append(Record(name=name, attributes=attrs or None))
                elif name_keywords:
                    # Fallback: check if line contains any keyword
                    for kw in name_keywords:
                        if kw in line:
                            records.append(Record(name=line))
                            break

        return records

    # ── YAML reader ─────────────────────────────────────────────────

    def _read_yaml(self, path: Path, config: dict) -> list[Record]:
        if yaml is None:
            raise ImportError("pyyaml is required to read .yaml files")

        with open(path, encoding=config.get("encoding", "utf-8")) as f:
            data = yaml.safe_load(f)

        record_path = config.get("record_path", "")
        if record_path:
            for key in record_path.split("."):
                if isinstance(data, dict):
                    data = data.get(key, {})
                else:
                    data = {}

        if not isinstance(data, list):
            if isinstance(data, dict):
                data = list(data.values()) if hasattr(data, "values") else []
            else:
                data = []

        mapping = config.get("field_mapping", {})
        filters = config.get("filters", [])

        records: list[Record] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            # Apply filters
            if not self._apply_filters(item, filters):
                continue

            rec = Record()
            for record_key, source_field in mapping.items():
                val = item.get(source_field, "")
                if record_key == "name":
                    rec.name = str(val).strip()
                elif record_key == "id":
                    rec.id = str(val).strip()
                else:
                    if "attributes" not in rec:
                        rec.attributes = {}
                    rec.attributes[record_key] = str(val).strip() if val else ""

            if rec.get("name"):
                records.append(rec)

        return records

    def _apply_filters(self, item: dict, filters: list[dict]) -> bool:
        for f in filters:
            field = f.get("field", "")
            val = str(item.get(field, "")).strip()

            if "pattern" in f:
                if not re.search(f["pattern"], val):
                    return False
            if "keywords" in f:
                if not any(kw in val for kw in f["keywords"]):
                    return False
        return True

    # ── Directory scanner ───────────────────────────────────────────

    def _read_directory(self, path: Path, config: dict) -> list[Record]:
        file_patterns = config.get("file_patterns", ["*.xlsx", "*.csv", "*.txt"])
        recursive = config.get("recursive", False)

        records: list[Record] = []
        for pattern in file_patterns:
            files = path.rglob(pattern) if recursive else path.glob(pattern)
            for fpath in sorted(files):
                if fpath.is_file():
                    records.append(
                        Record(
                            name=fpath.stem,
                            attributes={
                                "path": str(fpath),
                                "ext": fpath.suffix,
                                "filename": fpath.name,
                            },
                        )
                    )

        return records
