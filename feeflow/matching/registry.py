"""Generic entity registry with multi-layer indexing and name resolution."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from feeflow.matching.engine import EntityMatchingEngine

logger = logging.getLogger(__name__)


@dataclass
class EntityRecord:
    """A generic entity aggregating all known name variants and metadata.

    Domain-specific data goes into the ``attributes`` dict.
    """

    id: str  # canonical name serves as ID
    aliases: list[str] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def add_alias(self, alias: str) -> None:
        if alias and alias not in self.aliases:
            self.aliases.append(alias)

    def all_name_variants(self) -> list[str]:
        seen: list[str] = []
        for name in [self.id] + self.aliases:
            if name and name not in seen:
                seen.append(name)
        return seen


def _build_ngrams(text: str, n: int = 2) -> set[str]:
    """Extract character n-grams from Chinese text."""
    chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    return {"".join(chars[i : i + n]) for i in range(len(chars) - n + 1)}


class EntityRegistry:
    """In-memory entity registry with multi-layer indexing.

    Resolution order:
      1. ``_alias_index`` — O(1) exact match on normalized name
      2. ``_keyword_index`` — token-based pre-filter then exact match
      3. Fallback to injected ``EntityMatchingEngine`` (similarity scoring)
    """

    def __init__(self, engine: Optional[EntityMatchingEngine] = None):
        self._engine = engine
        self._entities: dict[str, EntityRecord] = {}
        self._alias_index: dict[str, str] = {}  # normalized_name → canonical id
        self._keyword_index: dict[str, list[str]] = {}  # ngram → [canonical ids]
        self._dirty = True  # keyword index needs rebuild

    # ── Entity management ───────────────────────────────────────────

    def get_or_create(self, name: str, attributes: Optional[dict] = None) -> EntityRecord:
        """Get existing entity by name, or create a new one."""
        existing = self.resolve(name)
        if existing:
            return existing

        entity = EntityRecord(id=name, attributes=attributes or {})
        self._entities[name] = entity
        self._alias_index[self._norm(name)] = name
        self._dirty = True
        return entity

    def register(self, entity: EntityRecord) -> None:
        """Register an already-constructed entity."""
        if entity.id in self._entities:
            logger.debug("Entity %r already registered, skipping", entity.id)
            return
        self._entities[entity.id] = entity
        self._alias_index[self._norm(entity.id)] = entity.id
        for alias in entity.aliases:
            self._alias_index[self._norm(alias)] = entity.id
        self._dirty = True

    def merge(self, source_id: str, target_id: str) -> EntityRecord:
        """Merge all data from source entity into target, then delete source."""
        source = self._entities.get(source_id)
        target = self._entities.get(target_id)
        if not source or not target:
            raise ValueError(f"Cannot merge {source_id} → {target_id}: entity not found")

        for alias in source.aliases:
            target.add_alias(alias)
        for k, v in source.attributes.items():
            if k not in target.attributes:
                target.attributes[k] = v
        for tag in source.tags:
            if tag not in target.tags:
                target.tags.append(tag)

        del self._entities[source_id]
        # Update alias index for all source aliases to point to target
        for alias in source.all_name_variants():
            self._alias_index[self._norm(alias)] = target_id

        self._dirty = True
        return target

    # ── Name resolution ─────────────────────────────────────────────

    def resolve(self, name: str) -> Optional[EntityRecord]:
        """Resolve a name to an entity, or None."""
        entity, _ = self.resolve_with_score(name)
        return entity

    def resolve_with_score(
        self, name: str
    ) -> tuple[Optional[EntityRecord], float]:
        """Resolve a name to (entity, confidence_score)."""
        norm = self._norm(name)
        if not norm:
            return None, 0.0

        # Step 1: Alias index O(1)
        canonical = self._alias_index.get(norm)
        if canonical and canonical in self._entities:
            return self._entities[canonical], 100.0

        # Step 2: Keyword index pre-filter + exact match
        candidates = self._keyword_candidates(norm, limit=50)
        if candidates:
            # Check if any candidate's normalized name matches exactly
            for cid in candidates:
                if cid not in self._entities:
                    continue
                entity = self._entities[cid]
                for variant in entity.all_name_variants():
                    if self._norm(variant) == norm:
                        return entity, 100.0

        # Step 3: Similarity matching via engine
        if self._engine and candidates:
            result = self._engine.best_match(norm, candidates)
            if result and result.score > 0:
                entity = self._entities.get(result.matched_value)
                if entity and self._engine.verify_match(entity.id, norm, result.score):
                    return entity, result.score

        return None, 0.0

    # ── Queries ─────────────────────────────────────────────────────

    def get_all(self) -> list[EntityRecord]:
        return list(self._entities.values())

    def get_entity(self, entity_id: str) -> Optional[EntityRecord]:
        return self._entities.get(entity_id)

    def entity_count(self) -> int:
        return len(self._entities)

    def search(self, tags: Optional[list[str]] = None, attribute_filter: Optional[dict] = None) -> list[EntityRecord]:
        """Filter entities by tags and/or attribute key-value pairs."""
        results = self.get_all()

        if tags:
            tag_set = set(tags)
            results = [e for e in results if tag_set.intersection(e.tags)]

        if attribute_filter:
            for k, v in attribute_filter.items():
                results = [e for e in results if e.attributes.get(k) == v]

        return results

    def summary(self) -> dict:
        return {
            "total_entities": len(self._entities),
            "total_aliases": sum(len(e.aliases) for e in self._entities.values()),
        }

    # ── Index internals ─────────────────────────────────────────────

    @staticmethod
    def _norm(name: str) -> str:
        """Basic normalization: strip whitespace."""
        return "".join(name.split())

    def _rebuild_keyword_index(self) -> None:
        """Rebuild n-gram keyword index from all entity names."""
        self._keyword_index.clear()
        for entity in self._entities.values():
            for variant in entity.all_name_variants():
                for ngram in _build_ngrams(variant):
                    self._keyword_index.setdefault(ngram, []).append(entity.id)
        # Deduplicate
        for key in self._keyword_index:
            seen: list[str] = []
            for eid in self._keyword_index[key]:
                if eid not in seen:
                    seen.append(eid)
            self._keyword_index[key] = seen
        self._dirty = False

    def _keyword_candidates(self, norm: str, limit: int = 50) -> list[str]:
        """Collect candidate entity IDs whose n-grams overlap with query."""
        if self._dirty:
            self._rebuild_keyword_index()

        query_ngrams = _build_ngrams(norm)
        if not query_ngrams:
            return []

        scores: dict[str, int] = {}
        for ngram in query_ngrams:
            for eid in self._keyword_index.get(ngram, []):
                scores[eid] = scores.get(eid, 0) + 1

        # Sort by overlap count descending
        sorted_ids = sorted(scores, key=lambda eid: scores[eid], reverse=True)
        return sorted_ids[:limit]
