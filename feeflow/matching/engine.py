"""Generic entity matching engine — orchestrates strategies with configurable verification."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from feeflow.matching.strategies import (
    MatchResult,
    MatchStrategy,
    get_strategy_class,
)

logger = logging.getLogger(__name__)


@dataclass
class MatchingConfig:
    """Configuration for the matching engine.

    All thresholds and verification rules are configurable.
    """

    strategies: list[MatchStrategy] = field(default_factory=list)
    min_score: float = 60.0
    auto_match_score: float = 95.0
    meaningful_match_fn: Optional[Callable[[str, str, float], bool]] = None

    @classmethod
    def from_dict(
        cls,
        config: dict,
        normalizer,
        strategy_registry: Optional[dict[str, type[MatchStrategy]]] = None,
    ) -> MatchingConfig:
        """Build MatchingConfig from a YAML/JSON dict.

        Expected format::

            {
                "strategies": [{"type": "exact", "exact_score": 100.0}, ...],
                "thresholds": {"min_score": 60.0, "auto_match": 95.0},
            }
        """
        registry = strategy_registry or {}

        built: list[MatchStrategy] = []
        for item in config.get("strategies", []):
            stype = item.pop("type")
            cls_ = registry.get(stype) or get_strategy_class(stype)
            if cls_ is None:
                logger.warning("Unknown strategy type %r, skipping", stype)
                continue
            built.append(cls_(normalizer=normalizer, **item))

        thr = config.get("thresholds", {})
        return cls(
            strategies=built,
            min_score=thr.get("min_score", 60.0),
            auto_match_score=thr.get("auto_match", 95.0),
        )


class EntityMatchingEngine:
    """Orchestrates multiple strategies in order.

    Usage::

        engine = EntityMatchingEngine(config)
        result = engine.best_match("四川美康", ["四川美康医药", "四川美康软件"])
    """

    def __init__(self, config: MatchingConfig):
        self.config = config

    def best_match(self, query: str, candidates: list[str]) -> MatchResult:
        """Run all strategies on all candidates, return the best match.

        Returns a ``MatchResult`` with score=0 and strategy="no_match"
        if no candidate exceeds ``min_score``.
        """
        best = MatchResult(0.0, "no_match", "")

        for candidate in candidates:
            for strategy in self.config.strategies:
                result = strategy.match(query, candidate)
                if result and result.score > best.score:
                    best = result
                    # Short-circuit on perfect match
                    if result.score >= 100.0:
                        return best

        if best.score < self.config.min_score:
            return MatchResult(0.0, "no_match", "")

        return best

    def verify_match(
        self, entity_name: str, query_name: str, raw_confidence: float
    ) -> bool:
        """Run false-positive verification, if configured."""
        fn = self.config.meaningful_match_fn
        if fn is None:
            return True  # no verification configured
        return fn(entity_name, query_name, raw_confidence)
