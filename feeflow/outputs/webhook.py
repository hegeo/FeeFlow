"""Webhook output adapter — posts data to an HTTP endpoint."""

from __future__ import annotations

import json
import logging
from typing import Any

from feeflow.outputs.base import OutputAdapter

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError
except ImportError:
    Request = None  # type: ignore

logger = logging.getLogger(__name__)


class WebhookOutputAdapter(OutputAdapter):
    """Posts data to an HTTP endpoint as JSON.

    Config options::

        url: str                      # Webhook URL
        method: str                   # HTTP method (default "POST")
        headers: dict                 # Custom headers
        payload_template: dict        # JSON payload template
    """

    name = "webhook"

    def write(self, data: list[dict], schema: dict, config: dict) -> str:
        url = config.get("url", "")
        if not url:
            logger.error("Webhook URL not configured")
            return ""

        method = config.get("method", "POST").upper()
        headers = config.get("headers", {})
        headers.setdefault("Content-Type", "application/json")

        # Build payload from template
        template = config.get("payload_template", {})
        payload = self._render_template(template, data)

        try:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            req = Request(url, data=body, method=method, headers=headers)
            with urlopen(req, timeout=30) as resp:
                logger.info("Webhook %s -> %s (status=%d)", method, url, resp.status)
                return url
        except URLError as e:
            logger.error("Webhook failed: %s", e)
            return ""

    def execute_action(self, action: dict, context: dict) -> dict:
        config = action.get("config", {})
        url = self.write([], {}, config)
        return {"status": "ok" if url else "error", "url": url}

    @staticmethod
    def _render_template(template: dict, data: list[dict]) -> dict:
        """Render a simple template with {{placeholders}} from data."""
        import re

        def _replace(val: Any) -> Any:
            if isinstance(val, str):
                # Support simple placeholders
                val = re.sub(r"\{\{rows\|join\('([^']+)', '([^']+)'\)\}\}", _join_rows, val)
                val = re.sub(r"\{\{rows\.(\d+)\.(\w+)\}\}", _row_value, val)
                return val
            if isinstance(val, dict):
                return {k: _replace(v) for k, v in val.items()}
            if isinstance(val, list):
                return [_replace(v) for v in val]
            return val

        def _join_rows(m):
            sep = m.group(1)
            key = m.group(2)
            return sep.join(str(r.get(key, "")) for r in data)

        def _row_value(m):
            idx = int(m.group(1))
            key = m.group(2)
            return str(data[idx].get(key, "")) if idx < len(data) else ""

        return _replace(template)
