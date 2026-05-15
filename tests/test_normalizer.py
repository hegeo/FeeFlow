"""Tests for PipelineNormalizer and all rule types."""

from feeflow.matching.normalizer import (
    PipelineNormalizer,
    StripPrefixRule,
    StripSuffixRule,
    StripRegexRule,
    CollapseWhitespaceRule,
    LowerRule,
    StripRegexMultipleRule,
)


def test_strip_prefix():
    rule = StripPrefixRule([r"^[VDG]-+\s*"])
    assert rule.apply("V-人民医院") == "人民医院"
    assert rule.apply("D-中心医院") == "中心医院"
    assert rule.apply("G-卫生院") == "卫生院"
    assert rule.apply("人民医院") == "人民医院"  # No change


def test_strip_suffix():
    rule = StripSuffixRule(["有限公司", "项目"])
    assert rule.apply("四川美康有限公司") == "四川美康"
    assert rule.apply("集采项目") == "集采"
    assert rule.apply("人民医院") == "人民医院"


def test_strip_regex():
    rule = StripRegexRule([r"PASS系统交流群", r"沟通群"])
    assert rule.apply("人民医院PASS系统交流群") == "人民医院"
    assert rule.apply("中心医院沟通群") == "中心医院"


def test_collapse_whitespace():
    rule = CollapseWhitespaceRule()
    assert rule.apply("人民医院 中心") == "人民医院中心"


def test_lower():
    rule = LowerRule()
    assert rule.apply("ABC医院") == "abc医院"


def test_pipeline():
    normalizer = PipelineNormalizer([
        StripPrefixRule([r"^[VDG]-+\s*"]),
        StripSuffixRule(["有限公司"]),
        CollapseWhitespaceRule(),
    ])
    assert normalizer.normalize("V- 四川美康有限公司") == "四川美康"


def test_pipeline_from_config():
    config = {
        "rules": [
            {"type": "strip_prefix", "patterns": ["^[VDG]-+\\s*"]},
            {"type": "strip_suffix", "words": ["有限公司", "项目"]},
            {"type": "collapse_whitespace"},
        ]
    }
    normalizer = PipelineNormalizer.from_config(config)
    result = normalizer.normalize("V- 人民 医院 有限公司")
    assert result == "人民医院"


def test_from_config_unknown_rule():
    import pytest
    config = {"rules": [{"type": "nonexistent"}]}
    with pytest.raises(ValueError, match="Unknown normalization rule type"):
        PipelineNormalizer.from_config(config)


def test_strip_regex_multi():
    rule = StripRegexMultipleRule([r"PASS|PIP|VBP"])
    assert rule.apply("VBP-PASS人民医院") == "-人民医院"
    assert rule.apply("VBP人民医院") == "人民医院"


def test_normalize_batch():
    normalizer = PipelineNormalizer([
        StripPrefixRule([r"^[VDG]-+\s*"]),
        CollapseWhitespaceRule(),
    ])
    texts = ["V- 人民医院", "D- 中心医院", "普通医院"]
    results = normalizer.normalize_batch(texts)
    assert results == ["人民医院", "中心医院", "普通医院"]
