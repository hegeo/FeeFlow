"""Platform action output adapter — delegates actions to a PlatformAdapter."""

from __future__ import annotations

import logging

from feeflow.outputs.base import OutputAdapter

logger = logging.getLogger(__name__)


class PlatformActionOutputAdapter(OutputAdapter):
    """Executes automation actions via a PlatformAdapter.

    Config options::

        platform: str                 # Platform adapter name
        action: str                   # Action name (quit_group, send_message, ...)
        batch: bool                   # Execute on all data rows
        confirm_threshold: float       # Confidence threshold for action
    """

    name = "platform_action"

    def write(self, data: list[dict], schema: dict, config: dict) -> str:
        """Not applicable — this adapter delegates to execute_action."""
        logger.warning("platform_action adapter does not support write(), use execute_action()")
        return ""

    def execute_action(self, action: dict, context: dict) -> dict:
        config = action.get("config", {})
        platform_name = config.get("platform", "")
        action_name = config.get("action", "")
        batch = config.get("batch", False)

        platform = context.get("platforms", {}).get(platform_name)
        if not platform:
            return {"status": "error", "message": f"Platform {platform_name!r} not found"}

        data = context.get("data", [])
        threshold = config.get("confirm_threshold", 0.0)

        if batch:
            results = []
            for row in data:
                if self._check_threshold(row, threshold):
                    ok = self._do_action(platform, action_name, row, config)
                    results.append({"row": row.get("canonical_name", ""), "ok": ok})
            return {"status": "ok", "results": results}
        else:
            ok = self._do_action(platform, action_name, data[0] if data else {}, config)
            return {"status": "ok" if ok else "error"}

    @staticmethod
    def _check_threshold(row: dict, threshold: float) -> bool:
        groups = row.get("wechat_groups", [])
        if not groups:
            return False
        best = max(g.get("match_confidence", 0.0) for g in groups)
        return best >= threshold

    @staticmethod
    def _do_action(platform, action_name: str, row: dict, config: dict) -> bool:
        if action_name == "quit_group":
            group_name = row.get("canonical_name", "")
            return platform.quit_group(group_name, config)
        elif action_name == "send_message":
            target = row.get("canonical_name", "")
            message = config.get("message", "Automated notification")
            return platform.send_message(target, message, config)
        else:
            logger.warning("Unknown action: %s", action_name)
            return False
