"""FeeFlow (飞流) CLI entry point."""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

import click

from feeflow import __version__

logger = logging.getLogger(__name__)


def _fix_gbk_stdio() -> None:
    """Wrap stdout/stderr with UTF-8 on Windows GBK terminals."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "buffer"):
            enc = getattr(stream, "encoding", "")
            if enc and enc.lower() in ("gbk", "gb2312", "gb18030"):
                wrapper = io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace")
                setattr(sys, stream_name, wrapper)


_fix_gbk_stdio()


@click.group()
@click.version_option(version=__version__)
def cli():
    """FeeFlow (飞流) — Entity Matching & Automation Workflow Platform"""


@cli.command()
@click.argument("workflow_file", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--env", "-e", "env_overrides", multiple=True, help="Override config vars (KEY=VALUE)")
def run(workflow_file: str, verbose: bool, env_overrides: list[str]) -> None:
    """Execute a workflow defined in YAML."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Apply env overrides
    for override in env_overrides:
        if "=" in override:
            k, v = override.split("=", 1)
            import os
            os.environ[k] = v

    from feeflow.workflow.loader import load_workflow, validate_workflow
    from feeflow.workflow.pipeline import PipelineRunner

    config = load_workflow(Path(workflow_file))

    errors = validate_workflow(config)
    if errors:
        click.echo("Configuration errors:", err=True)
        for e in errors:
            click.echo(f"  - {e}", err=True)
        sys.exit(1)

    runner = PipelineRunner(config)
    summary = runner.run()

    click.echo()
    click.echo("Pipeline complete:")
    click.echo(f"  Elapsed: {summary['elapsed_seconds']:.1f}s")
    click.echo(f"  Entities: {summary['total_entities']}")
    for output_id, result in summary.get("outputs", {}).items():
        click.echo(f"  Output {output_id}: {result}")


@cli.command()
def plugins() -> None:
    """List all discovered plugins."""
    from feeflow.plugins.discovery import PluginManager

    pm = PluginManager()
    pm.discover_all()
    summary = pm.summary()

    click.echo("Discovered plugins:")
    for category, names in summary.items():
        click.echo(f"  {category}:")
        for name in names:
            click.echo(f"    - {name}")


@cli.command()
@click.argument("workflow_file", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True)
def validate(workflow_file: str, verbose: bool) -> None:
    """Validate a workflow YAML without executing it."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    from feeflow.workflow.loader import load_workflow, validate_workflow

    try:
        config = load_workflow(Path(workflow_file))
    except Exception as e:
        click.echo(f"Failed to load workflow: {e}", err=True)
        sys.exit(1)

    errors = validate_workflow(config)
    if errors:
        for e in errors:
            click.echo(f"  - {e}")
        sys.exit(1)
    else:
        click.echo("Workflow is valid.")


@cli.command()
@click.argument("name")
@click.option("--dir", "-d", "output_dir", default=".", help="Output directory")
def init(name: str, output_dir: str) -> None:
    """Generate a workflow template."""
    from feeflow.workflow.loader import load_workflow

    template = {
        "workflow": {
            "name": name,
            "version": "1.0",
            "normalizer": {
                "rules": [
                    {"type": "collapse_whitespace"},
                ]
            },
            "matching": {
                "thresholds": {
                    "min_score": 60.0,
                    "auto_match": 95.0,
                },
                "strategies": [
                    {"type": "exact", "exact_score": 100.0},
                    {"type": "token", "containment_score": 90.0},
                    {"type": "fuzzy", "threshold": 85.0},
                ],
            },
            "sources": [
                {
                    "id": "source_1",
                    "adapter": "file",
                    "phase": 1,
                    "config": {
                        "path": "data.xlsx",
                        "format": "xlsx",
                        "column_mapping": {
                            "name": "名称",
                            "id": "ID",
                        },
                    },
                }
            ],
            "outputs": [
                {
                    "id": "report",
                    "adapter": "excel",
                    "config": {
                        "file": "output/report.xlsx",
                        "columns": [
                            {"key": "canonical_name", "header": "名称", "width": 30},
                        ],
                    },
                }
            ],
        }
    }

    import yaml

    out_path = Path(output_dir) / f"{name}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(template, f, allow_unicode=True, default_flow_style=False)

    click.echo(f"Template written to {out_path}")
