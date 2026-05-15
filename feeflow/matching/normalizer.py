"""Composable normalization pipeline — replaces hardcoded normalize_hospital_name()."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Optional


class NormalizationRule(ABC):
    """A single composable text normalization transform."""

    name: str = "unnamed_rule"

    @abstractmethod
    def apply(self, text: str) -> str:
        """Apply this normalization rule to the input text."""


class StripPrefixRule(NormalizationRule):
    """Remove leading patterns matching any of the given regex patterns."""

    name = "strip_prefix"

    def __init__(self, patterns: list[str]):
        self._compiled = [re.compile(p) for p in patterns]

    def apply(self, text: str) -> str:
        for pattern in self._compiled:
            text = pattern.sub("", text)
        return text


class StripSuffixRule(NormalizationRule):
    """Remove trailing words if the text ends with any of them."""

    name = "strip_suffix"

    def __init__(self, words: list[str]):
        # Sort longest first so longer matches take priority
        self.words = sorted(words, key=len, reverse=True)

    def apply(self, text: str) -> str:
        for w in self.words:
            if text.endswith(w):
                text = text[: -len(w)]
                break
        return text


class StripRegexRule(NormalizationRule):
    """Remove all matches of given regex patterns from the text."""

    name = "strip_regex"

    def __init__(self, patterns: list[str]):
        self._compiled = [re.compile(p) for p in patterns]

    def apply(self, text: str) -> str:
        for pattern in self._compiled:
            text = pattern.sub("", text)
        return text


class CollapseWhitespaceRule(NormalizationRule):
    """Replace all whitespace runs with empty string."""

    name = "collapse_whitespace"

    def apply(self, text: str) -> str:
        return re.sub(r"\s+", "", text)


class LowerRule(NormalizationRule):
    """Convert text to lowercase."""

    name = "lower"

    def apply(self, text: str) -> str:
        return text.lower()


class StripRegexMultipleRule(NormalizationRule):
    """Remove ALL matches of ALL given patterns repeatedly until no change."""

    name = "strip_regex_multi"

    def __init__(self, patterns: list[str]):
        self._compiled = [re.compile(p) for p in patterns]

    def apply(self, text: str) -> str:
        prev = None
        while prev != text:
            prev = text
            for pattern in self._compiled:
                text = pattern.sub("", text)
        return text


# ── Built-in rule registry ──────────────────────────────────────────

_BUILTIN_RULES: dict[str, type[NormalizationRule]] = {
    "strip_prefix": StripPrefixRule,
    "strip_suffix": StripSuffixRule,
    "strip_regex": StripRegexRule,
    "collapse_whitespace": CollapseWhitespaceRule,
    "lower": LowerRule,
    "strip_regex_multi": StripRegexMultipleRule,
}


def register_rule_type(name: str, cls: type[NormalizationRule]) -> None:
    """Register a custom rule type for YAML deserialization."""
    _BUILTIN_RULES[name] = cls


def get_rule_type(name: str) -> Optional[type[NormalizationRule]]:
    """Look up a rule type by name."""
    return _BUILTIN_RULES.get(name)


class PipelineNormalizer:
    """Composable normalization pipeline.

    Build from a list of NormalizationRule instances, or from YAML config::

        normalizer = PipelineNormalizer.from_config({
            "rules": [
                {"type": "strip_prefix", "patterns": ["^[VDG]-+\\\\s*"]},
                {"type": "strip_suffix", "words": ["有限公司", "项目"]},
                {"type": "collapse_whitespace"},
            ]
        })
    """

    def __init__(self, rules: list[NormalizationRule]):
        self.rules = rules

    def normalize(self, text: str) -> str:
        """Run all rules in sequence."""
        for rule in self.rules:
            text = rule.apply(text)
        return text

    def normalize_batch(self, texts: list[str]) -> list[str]:
        return [self.normalize(t) for t in texts]

    @classmethod
    def from_config(cls, config: dict) -> PipelineNormalizer:
        """Build a normalizer from a YAML/JSON config dict.

        Config format::

            {"rules": [
                {"type": "strip_prefix", "patterns": [...]},
                {"type": "strip_suffix", "words": [...]},
                {"type": "collapse_whitespace"},
            ]}
        """
        rules: list[NormalizationRule] = []
        for item in config.get("rules", []):
            rule_type = item.pop("type")
            cls_ = get_rule_type(rule_type)
            if cls_ is None:
                raise ValueError(f"Unknown normalization rule type: {rule_type!r}")
            rules.append(cls_(**item))
        return cls(rules)

    def __repr__(self) -> str:
        return f"PipelineNormalizer({[r.name for r in self.rules]})"
