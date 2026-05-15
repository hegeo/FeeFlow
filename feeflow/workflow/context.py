"""Workflow execution context — shared state across pipeline steps."""

from __future__ import annotations

from feeflow.matching.engine import EntityMatchingEngine
from feeflow.matching.normalizer import PipelineNormalizer
from feeflow.matching.registry import EntityRegistry
from feeflow.plugins.discovery import PluginManager


class WorkflowContext(dict):
    """Shared execution context accessible by all pipeline stages.

    Behaves as a dict so adapters can access it easily::

        platform = context["platforms"]["wechat"]
        registry = context.registry
    """

    def __init__(
        self,
        normalizer: PipelineNormalizer,
        engine: EntityMatchingEngine,
        registry: EntityRegistry,
        plugin_manager: PluginManager,
        raw_config: dict,
    ):
        super().__init__()
        self.normalizer = normalizer
        self.engine = engine
        self.registry = registry
        self.plugin_manager = plugin_manager
        self.raw_config = raw_config
        self["normalizer"] = normalizer
        self["engine"] = engine
        self["registry"] = registry
        self["platforms"] = {}
        self["data"] = []
        self["outputs"] = {}
