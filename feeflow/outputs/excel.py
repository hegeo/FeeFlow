"""Excel output adapter — writes data to styled .xlsx files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from feeflow.outputs.base import OutputAdapter

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
except ImportError:
    Workbook = None  # type: ignore

logger = logging.getLogger(__name__)


class ExcelOutputAdapter(OutputAdapter):
    """Writes data to Excel (.xlsx) files with configurable columns and styling.

    Config options::

        file: str                     # Output file path
        sheet: str                    # Sheet name (default "Sheet1")
        multi_sheet: bool             # Multiple sheets mode
        sheets: list[dict]            # Sheet definitions for multi-sheet mode
            name: str                 #   Sheet name
            filter: dict              #   Row filter conditions
            columns: list[dict]       #   Column definitions
        columns: list[dict]           # Column definitions (single sheet)
        header_fill: str              # Header background color (default "4472C4")
    """

    name = "excel"

    def write(self, data: list[dict], schema: dict, config: dict) -> str:
        if Workbook is None:
            raise ImportError("openpyxl is required for Excel output")

        output_path = Path(config["file"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        wb = Workbook()
        header_fill = PatternFill(
            start_color=config.get("header_fill", "4472C4"),
            end_color=config.get("header_fill", "4472C4"),
            fill_type="solid",
        )
        header_font = Font(bold=True, color="FFFFFF")

        if config.get("multi_sheet"):
            sheets = config.get("sheets", [])
            for i, sheet_def in enumerate(sheets):
                ws = wb.create_sheet(title=sheet_def["name"], index=i)
                filtered = self._filter_rows(data, sheet_def.get("filter", {}))
                self._write_sheet(ws, filtered, sheet_def.get("columns", []), header_fill, header_font)
            # Remove default sheet
            if "Sheet" in wb.sheetnames:
                del wb["Sheet"]
        else:
            ws = wb.active
            ws.title = config.get("sheet", "Sheet1")
            self._write_sheet(ws, data, config.get("columns", []), header_fill, header_font)

        wb.save(str(output_path))
        logger.info("Written %d rows to %s", len(data), output_path)
        return str(output_path)

    def _write_sheet(self, ws, rows: list[dict], columns: list[dict], header_fill, header_font):
        if not columns:
            # Auto-detect columns from first row
            if rows:
                columns = [{"key": k, "header": k} for k in rows[0].keys()]
            else:
                return

        # Write headers
        for col_idx, col_def in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_def.get("header", col_def["key"]))
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

            # Column width
            width = col_def.get("width", 18)
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        # Write data
        for row_idx, row in enumerate(rows, start=2):
            for col_idx, col_def in enumerate(columns, start=1):
                key = col_def.get("key", "")
                value = self.resolve_column(row, key)

                # Handle computed fields
                if col_def.get("computed") and key == "product_status":
                    value = self._format_product_status(row)

                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.alignment = Alignment(wrap_text=True)

    def _filter_rows(self, data: list[dict], filters: dict) -> list[dict]:
        """Apply filter conditions to row data."""
        result = data[:]

        if filters.get("has_field"):
            field = filters["has_field"]
            result = [r for r in result if self.resolve_column(r, field)]

        if filters.get("has_tag"):
            tag = filters["has_tag"]
            result = [r for r in result if tag in r.get("tags", [])]

        min_conf = filters.get("max_confidence")
        if min_conf is not None:
            result = [
                r for r in result
                if self._best_confidence(r) >= min_conf
            ]

        return result

    @staticmethod
    def _best_confidence(row: dict) -> float:
        groups = row.get("wechat_groups", [])
        if not groups:
            return 0.0
        return max(g.get("match_confidence", 0.0) for g in groups)

    @staticmethod
    def _format_product_status(row: dict) -> str:
        ps = row.get("product_status", {})
        completed = [k for k, v in ps.items() if v is True]
        return "、".join(completed) if completed else ""
