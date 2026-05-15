"""Pipeline runner — executes workflow YAML definitions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from feeflow.matching.engine import EntityMatchingEngine, MatchingConfig
from feeflow.matching.normalizer import PipelineNormalizer
from feeflow.matching.registry import EntityRegistry
from feeflow.matching.strategies import get_strategy_class
from feeflow.plugins.discovery import PluginManager
from feeflow.sources.base import DataSource, Record
from feeflow.workflow.context import WorkflowContext
from feeflow.workflow.loader import load_workflow, validate_workflow

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Executes a workflow YAML definition through phased loading,
    entity resolution, enrichment, and output generation.
    """

    def __init__(self, config: dict, plugin_manager: Optional[PluginManager] = None):
        self.config = config
        self.wf = config.get("workflow", {})
        self.pm = plugin_manager or PluginManager()
        self.pm.discover_all()

    def run(self) -> dict:
        """Execute the full workflow pipeline.

        Returns summary dict with timing and counts.
        """
        import time

        t0 = time.time()

        # 1. Build normalizer
        normalizer_cfg = self.wf.get("normalizer", {})
        normalizer = PipelineNormalizer.from_config(normalizer_cfg)

        # 2. Build matching engine config
        matching_cfg = self.wf.get("matching", {})
        engine_config = MatchingConfig.from_dict(matching_cfg, normalizer)

        # 3. Create engine + registry
        engine = EntityMatchingEngine(engine_config)
        registry = EntityRegistry(engine=engine)

        # 4. Create context
        context = WorkflowContext(normalizer, engine, registry, self.pm, self.config)

        # 5. Phase 1: Normative sources → register entities
        phase1_sources = [s for s in self.wf.get("sources", []) if s.get("phase", 1) == 1]
        for src_cfg in phase1_sources:
            self._load_source(src_cfg, context, register_only=True)

        # 6. Rebuild keyword index
        registry._rebuild_keyword_index()  # type: ignore[protected-access]

        # 7. Phase 2: Matching sources → resolve and enrich
        phase2_sources = [s for s in self.wf.get("sources", []) if s.get("phase", 2) == 2]
        for src_cfg in phase2_sources:
            self._load_source(src_cfg, context, register_only=False)

        # 8. Enrichment steps
        for enrich_cfg in self.wf.get("enrichment", []):
            self._run_enrichment(enrich_cfg, context)

        # 9. Outputs
        for out_cfg in self.wf.get("outputs", []):
            self._run_output(out_cfg, context)

        elapsed = time.time() - t0
        summary = {
            "elapsed_seconds": round(elapsed, 1),
            "total_entities": registry.entity_count(),
            "outputs": list(context["outputs"].values()),
        }
        logger.info("Pipeline complete: %s", summary)
        return summary

    # ── Source loading ──────────────────────────────────────────────

    def _load_source(
        self, src_cfg: dict, context: WorkflowContext, register_only: bool
    ) -> None:
        adapter_name = src_cfg.get("adapter", "file")
        cls = self.pm.get_source(adapter_name)
        if cls is None:
            logger.warning("Source adapter %r not found, skipping %r", adapter_name, src_cfg.get("id"))
            return

        adapter: DataSource = cls()
        config = src_cfg.get("config", {})
        records = adapter.read(config)

        logger.info(
            "Source %r (%s): %d records",
            src_cfg.get("id"),
            adapter_name,
            len(records),
        )

        for rec in records:
            name = rec.get("name", "")
            if not name:
                continue

            if register_only:
                # Phase 1: register as normative entity
                context.registry.get_or_create(name, rec.get("attributes"))
            else:
                # Phase 2: try to resolve, or create new entity
                entity, score = context.registry.resolve_with_score(name)
                if entity:
                    # Enrich existing entity
                    for k, v in (rec.get("attributes") or {}).items():
                        if k not in entity.attributes:
                            entity.attributes[k] = v
                    entity.add_alias(name)
                else:
                    entity = context.registry.get_or_create(name, rec.get("attributes"))

    # ── Enrichment ──────────────────────────────────────────────────

    def _run_enrichment(self, enrich_cfg: dict, context: WorkflowContext) -> None:
        """Run enrichment step (e.g. attribute mapping from external file)."""
        enrich_type = enrich_cfg.get("type", "attribute_map")
        if enrich_type != "attribute_map":
            logger.warning("Unknown enrichment type: %s", enrich_type)
            return

        source_path = enrich_cfg.get("source", "")
        if not source_path:
            return

        # Load enrichment data
        cls = self.pm.get_source("file")
        if cls is None:
            return
        adapter: DataSource = cls()
        path = Path(source_path)
        records = adapter.read({"path": str(path), "format": path.suffix.lstrip(".")})

        match_method = enrich_cfg.get("match_method", "name_resolve")
        target_attr = enrich_cfg.get("target_attribute", "")

        if match_method == "name_resolve":
            for rec in records:
                name = rec.get("name", "")
                if not name:
                    continue
                entity = context.registry.resolve(name)
                if entity and target_attr:
                    val = rec.get("attributes", {}).get("value", name)
                    existing = entity.attributes.get(target_attr, [])
                    if isinstance(existing, list):
                        if val not in existing:
                            existing.append(val)
                    entity.attributes[target_attr] = existing

    # ── Output generation ───────────────────────────────────────────

    def _run_output(self, out_cfg: dict, context: WorkflowContext) -> None:
        adapter_name = out_cfg.get("adapter", "excel")
        cls = self.pm.get_output(adapter_name)
        if cls is None:
            logger.warning("Output adapter %r not found, skipping", adapter_name)
            return

        adapter = cls()
        config = out_cfg.get("config", {})

        # Collect data from registry
        data = self._collect_output_data(out_cfg, context)

        if adapter_name == "platform_action":
            result = adapter.execute_action(out_cfg, dict(context))
        else:
            result = adapter.write(data, {}, config)

        output_id = out_cfg.get("id", adapter_name)
        context["outputs"][output_id] = result
        logger.info("Output %r: %s", output_id, result)

    def _collect_output_data(self, out_cfg: dict, context: WorkflowContext) -> list[dict]:
        """Convert registry entities to output row dicts based on filter config."""
        entities = context.registry.get_all()
        rows: list[dict] = []

        for entity in entities:
            row = {
                "canonical_name": entity.id,
                "aliases": entity.aliases,
                "attributes": entity.attributes,
                "tags": entity.tags,
            }
            rows.append(row)

        return rows
