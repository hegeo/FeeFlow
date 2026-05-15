"""Tests for workflow loader and validator."""

from pathlib import Path
from feeflow.workflow.loader import load_workflow, validate_workflow


def test_load_workflow(tmp_path):
    wf_path = tmp_path / "test.yaml"
    wf_path.write_text("workflow:\n  name: test\n  sources: []\n", encoding="utf-8")
    config = load_workflow(wf_path)
    assert config["workflow"]["name"] == "test"


def test_load_workflow_not_dict(tmp_path):
    wf_path = tmp_path / "test.yaml"
    wf_path.write_text("just a string\n", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="must contain a YAML dict"):
        load_workflow(wf_path)


def test_validate_valid():
    config = {
        "workflow": {
            "sources": [
                {"id": "src1", "adapter": "file"},
            ]
        }
    }
    errors = validate_workflow(config)
    assert errors == []


def test_validate_missing_workflow():
    errors = validate_workflow({})
    assert "Missing top-level 'workflow' key" in errors


def test_validate_missing_sources():
    config = {"workflow": {}}
    errors = validate_workflow(config)
    assert "Missing 'sources' section" in " ".join(errors)


def test_validate_duplicate_ids():
    config = {
        "workflow": {
            "sources": [
                {"id": "src1", "adapter": "file"},
                {"id": "src1", "adapter": "csv"},
            ]
        }
    }
    errors = validate_workflow(config)
    assert any("Duplicate" in e for e in errors)


def test_validate_missing_adapter():
    config = {
        "workflow": {
            "sources": [
                {"id": "src1"},
            ]
        }
    }
    errors = validate_workflow(config)
    assert any("missing 'adapter'" in e for e in errors)


def test_variable_substitution():
    import os
    os.environ["TEST_VAR"] = "test_value"
    config = {
        "workflow": {
            "path": "${TEST_VAR}",
            "normal": "hello",
        }
    }
    from feeflow.workflow.loader import _resolve_vars
    resolved = _resolve_vars(config)
    assert resolved["workflow"]["path"] == "test_value"
    assert resolved["workflow"]["normal"] == "hello"
