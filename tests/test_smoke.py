"""Smoke tests for top-level CLI wiring (help text, no args, callbacks)."""

from __future__ import annotations

from typer.testing import CliRunner

from jltool.cli import app


def test_top_level_help_lists_all_subapps(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = result.stdout
    for sub in ("instances", "scripts", "fs", "keys", "account", "ls", "balance"):
        assert sub in out, f"missing {sub} in help output"


def test_no_args_shows_help(runner: CliRunner) -> None:
    result = runner.invoke(app, [])
    # no_args_is_help=True returns exit code 2 (or 0 in newer typer); both fine
    assert result.exit_code in (0, 2)
    assert "Usage" in result.stdout or "Usage" in (result.stderr or "")


def test_instances_help(runner: CliRunner) -> None:
    result = runner.invoke(app, ["instances", "--help"])
    assert result.exit_code == 0
    for cmd in ("list", "get", "create", "pause", "resume", "destroy", "rename", "pause-all", "ssh"):
        assert cmd in result.stdout, f"missing {cmd} in instances help"


def test_account_help(runner: CliRunner) -> None:
    result = runner.invoke(app, ["account", "--help"])
    assert result.exit_code == 0
    for cmd in ("balance", "metrics", "gpus", "templates"):
        assert cmd in result.stdout


def test_json_flag_recognized(runner: CliRunner, mock_client) -> None:
    """The global --json flag must be accepted before subcommand args."""
    mock_client.instances.list.return_value = []
    result = runner.invoke(app, ["--json", "instances", "list"])
    assert result.exit_code == 0
    # empty list serialized
    assert result.stdout.strip() == "[]"
