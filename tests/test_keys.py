"""Tests for the `jltool keys ...` subcommands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from jltool import cli
from jltool.cli import app

from .conftest import fake_key


def test_list_empty(runner: CliRunner, mock_client) -> None:
    mock_client.ssh_keys.list.return_value = []
    result = runner.invoke(app, ["keys", "list"])
    assert result.exit_code == 0
    assert "No SSH keys" in result.stdout


def test_list_renders(runner: CliRunner, mock_client) -> None:
    mock_client.ssh_keys.list.return_value = [
        fake_key(key_id=1, key_name="laptop"),
        fake_key(key_id=2, key_name="desktop"),
    ]
    result = runner.invoke(app, ["keys", "list"])
    assert result.exit_code == 0
    assert "laptop" in result.stdout
    assert "desktop" in result.stdout


def test_add_with_explicit_file(runner: CliRunner, mock_client, tmp_path: Path) -> None:
    f = tmp_path / "id_ed25519.pub"
    f.write_text("ssh-ed25519 AAAA... user@host\n")
    result = runner.invoke(app, ["keys", "add", "laptop", "--file", str(f)])
    assert result.exit_code == 0, result.stderr
    mock_client.ssh_keys.add.assert_called_once_with(
        ssh_key="ssh-ed25519 AAAA... user@host", key_name="laptop"
    )


def test_add_default_file_missing(
    runner: CliRunner, mock_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Default file path resolution should report a clean validation error if missing."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # ensures ~/.ssh/id_ed25519.pub absent
    result = runner.invoke(app, ["keys", "add", "laptop"])
    assert result.exit_code == cli.EXIT_VALIDATION
    assert "key file not found" in result.stderr
    mock_client.ssh_keys.add.assert_not_called()


def test_add_empty_file(runner: CliRunner, mock_client, tmp_path: Path) -> None:
    f = tmp_path / "empty.pub"
    f.write_text("   \n")
    result = runner.invoke(app, ["keys", "add", "laptop", "--file", str(f)])
    assert result.exit_code == cli.EXIT_VALIDATION
    assert "empty" in result.stderr
    mock_client.ssh_keys.add.assert_not_called()


def test_remove_with_yes(runner: CliRunner, mock_client) -> None:
    result = runner.invoke(app, ["keys", "remove", "11", "--yes"])
    assert result.exit_code == 0
    # SDK signature is `remove(key_id: str)` — CLI passes the raw arg through.
    mock_client.ssh_keys.remove.assert_called_once_with("11")


def test_remove_accepts_non_numeric_id(runner: CliRunner, mock_client) -> None:
    """Some keys carry UUID-style ids; the CLI must accept arbitrary strings."""
    result = runner.invoke(app, ["keys", "remove", "abc-123-uuid", "--yes"])
    assert result.exit_code == 0
    mock_client.ssh_keys.remove.assert_called_once_with("abc-123-uuid")


def test_remove_aborts(runner: CliRunner, mock_client) -> None:
    result = runner.invoke(app, ["keys", "remove", "11"], input="n\n")
    assert result.exit_code != 0
    mock_client.ssh_keys.remove.assert_not_called()
