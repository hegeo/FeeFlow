"""Plugin discovery and management."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PluginManager:
    """Discovers and manages plugins via entry points + explicit registration.

    Supports three discovery mechanisms:
      1. Python entry points (setuptools ``entry_points`` in pyproject.toml)
      2. Explicit registration (``register_*()`` methods)
      3. Filesystem scan of ``feeflow-plugins/`` directory
    """

    def __init__(self):
        self._sources: dict[str, type] = {}
        self._platforms: dict[str, type] = {}
        self._outputs: dict[str, type] = {}
        self._strategies: dict[str, type] = {}
        self._norm_rules: dict[str, type] = {}
        self._verification_rules: dict[str, type] = {}

        self._inited = False

    def discover_all(self) -> None:
        """Run all discovery mechanisms."""
        if self._inited:
            return
        self._discover_entry_points("feeflow.sources", self._sources)
        self._discover_entry_points("feeflow.platforms", self._platforms)
        self._discover_entry_points("feeflow.outputs", self._outputs)
        self._discover_entry_points("feeflow.strategies", self._strategies)
        self._discover_entry_points("feeflow.normalizer_rules", self._norm_rules)
        self._scan_plugin_directory()
        self._inited = True

    # ── Registration ────────────────────────────────────────────────

    def register_source(self, name: str, cls: type) -> None:
        self._sources[name] = cls

    def register_platform(self, name: str, cls: type) -> None:
        self._platforms[name] = cls

    def register_output(self, name: str, cls: type) -> None:
        self._outputs[name] = cls

    def register_strategy(self, name: str, cls: type) -> None:
        self._strategies[name] = cls

    def register_normalizer_rule(self, name: str, cls: type) -> None:
        self._norm_rules[name] = cls

    def register_verification_rule(self, name: str, cls: type) -> None:
        self._verification_rules[name] = cls

    # ── Lookup ──────────────────────────────────────────────────────

    def get_source(self, name: str) -> Optional[type]:
        return self._sources.get(name)

    def get_platform(self, name: str) -> Optional[type]:
        return self._platforms.get(name)

    def get_output(self, name: str) -> Optional[type]:
        return self._outputs.get(name)

    def get_strategy(self, name: str) -> Optional[type]:
        return self._strategies.get(name)

    def get_normalizer_rule(self, name: str) -> Optional[type]:
        return self._norm_rules.get(name)

    def get_verification_rule(self, name: str) -> Optional[type]:
        return self._verification_rules.get(name)

    # ── Listing ─────────────────────────────────────────────────────

    def list_sources(self) -> list[str]:
        return list(self._sources.keys())

    def list_platforms(self) -> list[str]:
        return list(self._platforms.keys())

    def list_outputs(self) -> list[str]:
        return list(self._outputs.keys())

    def list_strategies(self) -> list[str]:
        return list(self._strategies.keys())

    def list_normalizer_rules(self) -> list[str]:
        return list(self._norm_rules.keys())

    def summary(self) -> dict:
        return {
            "sources": self.list_sources(),
            "platforms": self.list_platforms(),
            "outputs": self.list_outputs(),
            "strategies": self.list_strategies(),
            "normalizer_rules": self.list_normalizer_rules(),
        }

    # ── Discovery internals ─────────────────────────────────────────

    @staticmethod
    def _discover_entry_points(group: str, registry: dict) -> None:
        try:
            from importlib.metadata import entry_points

            for ep in entry_points(group=group):
                try:
                    registry[ep.name] = ep.load()
                except Exception as e:
                    logger.debug("Failed to load entry point %s: %s", ep.name, e)
        except Exception:
            pass  # Not running as installed package

    def _scan_plugin_directory(self) -> None:
        """Scan feeflow-plugins/ for Python files exporting ADAPTERS."""
        plugin_dir = Path(__file__).resolve().parent.parent.parent / "feeflow-plugins"
        if not plugin_dir.exists():
            return

        for importer, modname, ispkg in pkgutil.iter_modules([str(plugin_dir)]):
            try:
                mod = importlib.import_module(f"feeflow-plugins.{modname}")
                if hasattr(mod, "ADAPTERS"):
                    adapters: dict = mod.ADAPTERS
                    for kind, name, cls in adapters:
                        if kind == "source":
                            self._sources[name] = cls
                        elif kind == "platform":
                            self._platforms[name] = cls
                        elif kind == "output":
                            self._outputs[name] = cls
                        elif kind == "strategy":
                            self._strategies[name] = cls
                        elif kind == "normalizer_rule":
                            self._norm_rules[name] = cls
                        elif kind == "verification_rule":
                            self._verification_rules[name] = cls
            except Exception as e:
                logger.warning("Failed to load plugin %s: %s", modname, e)
