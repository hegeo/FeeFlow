"""Tests for all matching strategies."""

from feeflow.matching.normalizer import (
    PipelineNormalizer,
    CollapseWhitespaceRule,
    StripPrefixRule,
)
from feeflow.matching.strategies import (
    ExactMatchStrategy,
    TokenMatchStrategy,
    FuzzyMatchStrategy,
    MatchResult,
)


def _make_normalizer():
    return PipelineNormalizer([
        StripPrefixRule([r"^[VDG]-+\s*"]),
        CollapseWhitespaceRule(),
    ])


class TestExactMatch:
    def test_exact_match(self):
        strategy = ExactMatchStrategy(_make_normalizer())
        result = strategy.match("人民医院", "人民医院")
        assert result is not None
        assert result.score == 100.0

    def test_normalized_match(self):
        strategy = ExactMatchStrategy(_make_normalizer())
        result = strategy.match("V-人民医院", "人民医院")
        assert result is not None
        assert result.score == 100.0

    def test_no_match(self):
        strategy = ExactMatchStrategy(_make_normalizer())
        result = strategy.match("人民医院", "中心医院")
        assert result is None

    def test_extra_normalizer(self):
        """Test extra normalizers for cross-field matching."""
        # Use a normalizer without CollapseWhitespaceRule so spaces
        # are not removed, and the extra normalizer is needed.
        normalizer_no_collapse = PipelineNormalizer([
            StripPrefixRule([r"^[VDG]-+\s*"]),
        ])
        strategy = ExactMatchStrategy(
            normalizer_no_collapse,
            extra_normalizers=[lambda s: s.replace(" ", "")],
        )
        # Query with spaces won't match directly without the extra normalizer
        result = strategy.match("人民 医院", "人民医院")
        assert result is not None
        assert result.score == 95.0  # exact_score - 5


class TestTokenMatch:
    def test_substring_containment(self):
        strategy = TokenMatchStrategy(_make_normalizer())
        result = strategy.match("川北医学院附属医院", "川北医学院")
        assert result is not None
        assert result.score == 90.0

    def test_token_overlap(self):
        strategy = TokenMatchStrategy(
            _make_normalizer(),
            token_overlap_min_ratio=0.5,
            token_overlap_min_score=80.0,
            token_overlap_max_score=95.0,
        )
        result = strategy.match("人民医院", "人民医院")
        assert result is not None

    def test_no_match(self):
        strategy = TokenMatchStrategy(_make_normalizer())
        result = strategy.match("人民医院", "中心小学")
        assert result is None or result.score < 80.0

    def test_generic_word_filter(self):
        """All-generic query returns None when generic tokens are filtered."""
        generic_pred = lambda s: s in {"人民医院", "中心医院", "卫生院"}
        strategy = TokenMatchStrategy(
            _make_normalizer(),
            generic_token_predicate=generic_pred,
        )
        # "人民医院" is a single continuous Chinese token, added to generic set
        result = strategy.match("人民医院", "人民医院")
        assert result is None  # All tokens filtered out

    def test_generic_word_meaningful_match(self):
        """Meaningful tokens still match even with generic words present."""
        generic_pred = lambda s: s in {"医院", "人民"}
        strategy = TokenMatchStrategy(
            _make_normalizer(),
            generic_token_predicate=generic_pred,
        )
        # "人民医院" is a 6-char token, NOT in {"医院", "人民"} (2-char entries)
        # So it should still match
        result = strategy.match("人民医院", "人民医院")
        assert result is not None

    def test_empty_normalized(self):
        strategy = TokenMatchStrategy(_make_normalizer())
        result = strategy.match("", "人民医院")
        assert result is None


class TestFuzzyMatch:
    def test_high_similarity(self):
        strategy = FuzzyMatchStrategy(_make_normalizer(), threshold=85.0)
        result = strategy.match("四川美康医药软件有限公司", "四川美康医药软件")
        # These are very similar, should exceed threshold
        assert result is not None
        assert result.score >= 85.0

    def test_low_similarity(self):
        strategy = FuzzyMatchStrategy(_make_normalizer(), threshold=85.0)
        # Very different strings
        result = strategy.match("人民医院", "中心小学")
        assert result is None or result.score < 85.0

    def test_lazy_import_rapidfuzz(self):
        """Ensure rapidfuzz is lazily imported."""
        strategy = FuzzyMatchStrategy(_make_normalizer())
        assert strategy._fuzz is None
        strategy.match("a", "b")
        assert strategy._fuzz is not None
