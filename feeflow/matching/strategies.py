"""Four matching strategies — domain-agnostic with injected normalizer."""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

from feeflow.matching.normalizer import PipelineNormalizer

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of a single strategy match."""

    score: float
    strategy_name: str
    matched_value: str = ""

    def __bool__(self) -> bool:
        return self.score > 0


class MatchStrategy(ABC):
    """Abstract base for all matching strategies.

    All domain-specific normalization is delegated to the injected
    ``PipelineNormalizer``.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def match(self, query: str, candidate: str) -> Optional[MatchResult]:
        """Compare query against candidate, return match result or None."""


# ── Layer 1: Exact match ────────────────────────────────────────────


class ExactMatchStrategy(MatchStrategy):
    """Match when normalized strings are identical.

    Supports an optional ``extra_normalizers`` list for additional
    transformations (e.g. WeChat prefix stripping, nickname suffix
    removal) that are tried in addition to the primary normalizer.
    """

    name = "exact"

    def __init__(
        self,
        normalizer: PipelineNormalizer,
        extra_normalizers: Optional[list[Callable[[str], str]]] = None,
        exact_score: float = 100.0,
    ):
        self.normalizer = normalizer
        self.extra_normalizers = extra_normalizers or []
        self.exact_score = exact_score

    def match(self, query: str, candidate: str) -> Optional[MatchResult]:
        query_norm = self.normalizer.normalize(query)
        candidate_norm = self.normalizer.normalize(candidate)

        # Primary: normalized equality
        if query_norm and query_norm == candidate_norm:
            return MatchResult(self.exact_score, self.name, candidate)

        # Extra: try additional normalizers (e.g. cross-match display vs nickname)
        for extra in self.extra_normalizers:
            q2 = extra(query_norm)
            c2 = extra(candidate_norm)
            if q2 and q2 == c2:
                return MatchResult(self.exact_score - 5, self.name, candidate)

        return None


# ── Layer 2: Token / substring match ────────────────────────────────


class TokenMatchStrategy(MatchStrategy):
    """Match based on token overlap or substring containment.

    Tokenization extracts Chinese character sequences of at least
    ``min_token_length``.  A configurable ``generic_token_predicate``
    can filter out domain-specific stop-words.
    """

    name = "token"

    def __init__(
        self,
        normalizer: PipelineNormalizer,
        min_token_length: int = 2,
        generic_token_predicate: Optional[Callable[[str], bool]] = None,
        containment_score: float = 90.0,
        token_overlap_min_ratio: float = 0.8,
        token_overlap_min_score: float = 80.0,
        token_overlap_max_score: float = 95.0,
    ):
        self.normalizer = normalizer
        self.min_token_length = min_token_length
        self.generic_pred = generic_token_predicate or (lambda _: False)
        self.containment_score = containment_score
        self.overlap_min_ratio = token_overlap_min_ratio
        self.overlap_min_score = token_overlap_min_score
        self.overlap_max_score = token_overlap_max_score

    def _tokenize(self, text: str) -> list[str]:
        """Extract meaningful tokens: Chinese sequences 2+ chars."""
        tokens: list[str] = []
        for seq in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            if not self.generic_pred(seq):
                tokens.append(seq)
        return tokens

    def match(self, query: str, candidate: str) -> Optional[MatchResult]:
        q_norm = self.normalizer.normalize(query)
        c_norm = self.normalizer.normalize(candidate)

        if not q_norm or not c_norm:
            return None

        # Tokenization with generic word filtering
        q_tokens = self._tokenize(q_norm)
        c_tokens = self._tokenize(c_norm)

        # If both sides have meaningful tokens, check containment
        if q_tokens and c_tokens:
            # Substring containment
            shorter, longer = (q_norm, c_norm) if len(q_norm) <= len(c_norm) else (c_norm, q_norm)
            if len(shorter) >= 3 and shorter in longer:
                return MatchResult(self.containment_score, self.name, candidate)

        # Token ratio
        if not q_tokens or not c_tokens:
            return None

        q_set = set(q_tokens)
        c_set = set(c_tokens)
        overlap = q_set & c_set

        if not overlap:
            return None

        q_ratio = len(overlap) / len(q_set)
        c_ratio = len(overlap) / len(c_set)
        best_ratio = max(q_ratio, c_ratio)

        if best_ratio >= self.overlap_min_ratio:
            score = self.overlap_min_score + 10.0 * best_ratio
            score = min(score, self.overlap_max_score)
            return MatchResult(score, self.name, candidate)

        return None


# ── Layer 3: Fuzzy string match (rapidfuzz) ─────────────────────────


class FuzzyMatchStrategy(MatchStrategy):
    """Rapidfuzz-based weighted similarity.

    Uses ``token_sort_ratio * token_sort_weight + partial_ratio * partial_weight``.
    """

    name = "fuzzy"

    def __init__(
        self,
        normalizer: PipelineNormalizer,
        threshold: float = 85.0,
        token_sort_weight: float = 0.6,
        partial_weight: float = 0.4,
    ):
        self.normalizer = normalizer
        self.threshold = threshold
        self.token_sort_weight = token_sort_weight
        self.partial_weight = partial_weight
        self._fuzz = None

    def _get_fuzz(self):
        if self._fuzz is None:
            import rapidfuzz.fuzz as _f

            self._fuzz = _f
        return self._fuzz

    def match(self, query: str, candidate: str) -> Optional[MatchResult]:
        q_norm = self.normalizer.normalize(query)
        c_norm = self.normalizer.normalize(candidate)

        if not q_norm or not c_norm:
            return None

        fuzz = self._get_fuzz()
        token_sort = fuzz.token_sort_ratio(q_norm, c_norm)
        partial = fuzz.partial_ratio(q_norm, c_norm)
        score = token_sort * self.token_sort_weight + partial * self.partial_weight

        if score >= self.threshold:
            return MatchResult(score, self.name, candidate)
        return None


# ── Layer 4: Phonetic match (pypinyin) ──────────────────────────────


class PhoneticMatchStrategy(MatchStrategy):
    """Pinyin-based fuzzy matching using pypinyin + rapidfuzz token_sort."""

    name = "phonetic"

    def __init__(
        self,
        normalizer: PipelineNormalizer,
        threshold: float = 90.0,
    ):
        self.normalizer = normalizer
        self.threshold = threshold
        self._pinyin = None
        self._fuzz = None

    def _get_pinyin(self):
        if self._pinyin is None:
            try:
                from pypinyin import lazy_pinyin

                self._pinyin = lazy_pinyin
            except ImportError:
                logger.warning("pypinyin not installed; PhoneticMatchStrategy disabled")
                self._pinyin = False
        return self._pinyin if self._pinyin is not False else None

    def _get_fuzz(self):
        if self._fuzz is None:
            import rapidfuzz.fuzz as _f

            self._fuzz = _f
        return self._fuzz

    def match(self, query: str, candidate: str) -> Optional[MatchResult]:
        lazy_pinyin = self._get_pinyin()
        if lazy_pinyin is None:
            return None

        q_norm = self.normalizer.normalize(query)
        c_norm = self.normalizer.normalize(candidate)

        if not q_norm or not c_norm:
            return None

        q_py = " ".join(lazy_pinyin(q_norm))
        c_py = " ".join(lazy_pinyin(c_norm))

        fuzz = self._get_fuzz()
        score = float(fuzz.token_sort_ratio(q_py, c_py))

        if score >= self.threshold:
            return MatchResult(score, self.name, candidate)
        return None


# ── Strategy registry for YAML deserialization ──────────────────────

_STRATEGY_REGISTRY: dict[str, type[MatchStrategy]] = {
    "exact": ExactMatchStrategy,
    "token": TokenMatchStrategy,
    "fuzzy": FuzzyMatchStrategy,
    "phonetic": PhoneticMatchStrategy,
}


def register_strategy(name: str, cls: type[MatchStrategy]) -> None:
    _STRATEGY_REGISTRY[name] = cls


def get_strategy_class(name: str) -> Optional[type[MatchStrategy]]:
    return _STRATEGY_REGISTRY.get(name)
