"""Tests for EntityMatchingEngine and MatchingConfig."""

from feeflow.matching.normalizer import PipelineNormalizer, CollapseWhitespaceRule
from feeflow.matching.engine import MatchingConfig, EntityMatchingEngine
from feeflow.matching.strategies import MatchResult


def _make_normalizer():
    return PipelineNormalizer([CollapseWhitespaceRule()])


class TestMatchingConfig:
    def test_from_dict(self):
        config_data = {
            "strategies": [
                {"type": "exact", "exact_score": 100.0},
                {"type": "token", "containment_score": 90.0},
            ],
            "thresholds": {"min_score": 60.0, "auto_match": 95.0},
        }
        config = MatchingConfig.from_dict(config_data, _make_normalizer())
        assert len(config.strategies) == 2
        assert config.min_score == 60.0
        assert config.auto_match_score == 95.0

    def test_empty_strategies(self):
        config = MatchingConfig.from_dict({}, _make_normalizer())
        assert len(config.strategies) == 0

    def test_unknown_strategy_skipped(self):
        config_data = {
            "strategies": [
                {"type": "nonexistent"},
                {"type": "exact"},
            ],
        }
        config = MatchingConfig.from_dict(config_data, _make_normalizer())
        assert len(config.strategies) == 1


class TestEntityMatchingEngine:
    def test_best_match_exact(self):
        config = MatchingConfig(strategies=[], min_score=0)
        engine = EntityMatchingEngine(config)
        # Without strategies, returns no_match
        result = engine.best_match("test", ["test", "other"])
        assert result.score == 0
        assert result.strategy_name == "no_match"

    def test_verify_match_no_fn(self):
        config = MatchingConfig()
        engine = EntityMatchingEngine(config)
        assert engine.verify_match("a", "b", 0.5) is True  # No verification fn

    def test_verify_match_with_fn(self):
        def always_false(entity, query, score):
            return False

        config = MatchingConfig(meaningful_match_fn=always_false)
        engine = EntityMatchingEngine(config)
        assert engine.verify_match("a", "b", 100.0) is False

    def test_verify_match_threshold(self):
        def threshold_fn(entity, query, score):
            return score >= 90.0

        config = MatchingConfig(meaningful_match_fn=threshold_fn)
        engine = EntityMatchingEngine(config)
        assert engine.verify_match("a", "b", 95.0) is True
        assert engine.verify_match("a", "b", 85.0) is False
