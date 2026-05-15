"""YAML workflow configuration loader and validator."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


def load_workflow(path: Path) -> dict:
    """Load and resolve a workflow YAML file.

    Performs variable substitution on ``${var_name}`` and
    ``${env:VAR_NAME}`` patterns.
    """
    if yaml is None:
        raise ImportError("pyyaml is required to load workflow files")

    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError(f"Workflow file {path} must contain a YAML dict")

    # Resolve variables
    config = _resolve_vars(config)

    return config


def validate_workflow(config: dict) -> list[str]:
    """Validate workflow configuration, return list of errors."""
    errors: list[str] = []

    if "workflow" not in config:
        errors.append("Missing top-level 'workflow' key")
        return errors

    wf = config["workflow"]

    if "sources" not in wf:
        errors.append("Missing 'sources' section in workflow")

    seen_ids: set[str] = set()
    for src in wf.get("sources", []):
        sid = src.get("id", "")
        if not sid:
            errors.append("Source missing 'id'")
        elif sid in seen_ids:
            errors.append(f"Duplicate source id: {sid}")
        else:
            seen_ids.add(sid)
        if "adapter" not in src:
            errors.append(f"Source {sid!r} missing 'adapter'")

    return errors


def _resolve_vars(obj: Any, env: Optional[dict] = None) -> Any:
    """Recursively resolve ${var} and ${env:VAR} in strings and dict values."""
    if env is None:
        env = dict(os.environ)

    if isinstance(obj, str):
        return _resolve_string(obj, env)
    elif isinstance(obj, dict):
        return {k: _resolve_vars(v, env) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_vars(item, env) for item in obj]
    return obj


_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]+))?\}")


def _resolve_string(text: str, env: dict) -> str:
    def _replacer(m: re.Match) -> str:
        var_expr = m.group(1)
        default = m.group(2)

        if var_expr.startswith("env:"):
            return env.get(var_expr[4:], default or "")
        else:
            return env.get(var_expr, default or var_expr)

    return _VAR_PATTERN.sub(_replacer, text)
