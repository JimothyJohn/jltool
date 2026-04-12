"""Tests for the `jltool scripts ...` subcommands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from jltool.cli import app

from .conftest import fake_script


def test_list_empty(runner: CliRunner, mock_client) -> None:
    mock_client.scripts.list.return_value = []
    result = runner.invoke(app, ["scripts", "list"])
    assert result.exit_code == 0
    assert "No scripts" in result.stdout


def test_list_renders(runner: CliRunner, mock_client) -> None:
    mock_client.scripts.list.return_value = [
        fake_script(script_id=1, script_name="bootstrap"),
        fake_script(script_id=2, script_name="install-deps"),
    ]
    result = runner.invoke(app, ["scripts", "list"])
    assert result.exit_code == 0
    assert "bootstrap" in result.stdout
    assert "install-deps" in result.stdout


def test_add_uploads_file_contents(runner: CliRunner, mock_client, tmp_path: Path) -> None:
    f = tmp_path / "init.sh"
    f.write_text("#!/bin/bash\npip install wandb\n")
    result = runner.invoke(app, ["scripts", "add", "deps", "--file", str(f)])
    assert result.exit_code == 0, result.stderr
    mock_client.scripts.add.assert_called_once_with(
        script="#!/bin/bash\npip install wandb\n", name="deps"
    )
    assert "Added" in result.stdout


def test_add_missing_file_errors(runner: CliRunner, mock_client, tmp_path: Path) -> None:
    bogus = tmp_path / "nope.sh"
    result = runner.invoke(app, ["scripts", "add", "deps", "--file", str(bogus)])
    assert result.exit_code != 0
    mock_client.scripts.add.assert_not_called()


def test_update(runner: CliRunner, mock_client, tmp_path: Path) -> None:
    f = tmp_path / "new.sh"
    f.write_text("echo hi")
    result = runner.invoke(app, ["scripts", "update", "7", "--file", str(f)])
    assert result.exit_code == 0
    mock_client.scripts.update.assert_called_once_with(script_id=7, script="echo hi")


def test_remove_with_yes(runner: CliRunner, mock_client) -> None:
    result = runner.invoke(app, ["scripts", "remove", "7", "--yes"])
    assert result.exit_code == 0
    mock_client.scripts.remove.assert_called_once_with(7)


def test_remove_aborts_without_confirm(runner: CliRunner, mock_client) -> None:
    result = runner.invoke(app, ["scripts", "remove", "7"], input="n\n")
    assert result.exit_code != 0
    mock_client.scripts.remove.assert_not_called()
