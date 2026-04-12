"""Tests for the `jltool fs ...` subcommands."""

from __future__ import annotations

from typer.testing import CliRunner

from jltool.cli import app

from .conftest import fake_fs


def test_list_empty(runner: CliRunner, mock_client) -> None:
    mock_client.filesystems.list.return_value = []
    result = runner.invoke(app, ["fs", "list"])
    assert result.exit_code == 0
    assert "No filesystems" in result.stdout


def test_list_renders(runner: CliRunner, mock_client) -> None:
    mock_client.filesystems.list.return_value = [
        fake_fs(fs_id=1, fs_name="datasets", storage=500),
        fake_fs(fs_id=2, fs_name="ckpts", storage=200),
    ]
    result = runner.invoke(app, ["fs", "list"])
    assert result.exit_code == 0
    assert "datasets" in result.stdout
    assert "ckpts" in result.stdout
    assert "500 GB" in result.stdout


def test_create(runner: CliRunner, mock_client) -> None:
    mock_client.filesystems.create.return_value = 99
    result = runner.invoke(app, ["fs", "create", "datasets", "--storage", "200"])
    assert result.exit_code == 0
    mock_client.filesystems.create.assert_called_once_with(fs_name="datasets", storage=200)
    assert "id=99" in result.stdout


def test_create_with_region(runner: CliRunner, mock_client) -> None:
    mock_client.filesystems.create.return_value = 100
    result = runner.invoke(
        app,
        ["fs", "create", "datasets", "--storage", "200", "--region", "india-noida-01"],
    )
    assert result.exit_code == 0
    mock_client.filesystems.create.assert_called_once_with(
        fs_name="datasets", storage=200, region="india-noida-01"
    )


def test_create_with_deployment_id(runner: CliRunner, mock_client) -> None:
    mock_client.filesystems.create.return_value = 101
    result = runner.invoke(
        app,
        [
            "fs", "create", "datasets",
            "--storage", "200",
            "--region", "india-01",
            "--deployment-id", "dep-xyz",
        ],
    )
    assert result.exit_code == 0
    mock_client.filesystems.create.assert_called_once_with(
        fs_name="datasets", storage=200, region="india-01", deployment_id="dep-xyz"
    )


def test_edit(runner: CliRunner, mock_client) -> None:
    mock_client.filesystems.edit.return_value = 7
    result = runner.invoke(app, ["fs", "edit", "7", "--storage", "500"])
    assert result.exit_code == 0
    mock_client.filesystems.edit.assert_called_once_with(fs_id=7, storage=500)


def test_remove_with_yes(runner: CliRunner, mock_client) -> None:
    result = runner.invoke(app, ["fs", "remove", "7", "--yes"])
    assert result.exit_code == 0
    mock_client.filesystems.remove.assert_called_once_with(7)


def test_remove_aborts(runner: CliRunner, mock_client) -> None:
    result = runner.invoke(app, ["fs", "remove", "7"], input="n\n")
    assert result.exit_code != 0
    mock_client.filesystems.remove.assert_not_called()
