"""Tests for SDK exception → exit code translation in jl_client."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from jarvislabs import (
    APIError,
    AuthError,
    InsufficientBalanceError,
    JarvislabsError,
    NotFoundError,
    SSHError,
    ValidationError,
)
from jltool import cli
from jltool.cli import app


def _provoke(mock_client, exc: Exception) -> None:
    """Make `instances list` raise the given exception."""
    mock_client.instances.list.side_effect = exc


def test_auth_error_exits_2(runner: CliRunner, mock_client) -> None:
    _provoke(mock_client, AuthError("nope"))
    result = runner.invoke(app, ["instances", "list"])
    assert result.exit_code == cli.EXIT_AUTH == 2
    assert "auth error" in result.stderr
    assert "JL_API_KEY" in result.stderr


def test_insufficient_balance_exits_6(runner: CliRunner, mock_client) -> None:
    _provoke(mock_client, InsufficientBalanceError("Insufficient balance"))
    result = runner.invoke(app, ["instances", "list"])
    assert result.exit_code == cli.EXIT_INSUFFICIENT_BALANCE == 6
    assert "insufficient balance" in result.stderr
    assert "jarvislabs.ai/settings" in result.stderr


def test_not_found_exits_3(runner: CliRunner, mock_client) -> None:
    mock_client.instances.get.side_effect = NotFoundError("no such instance")
    result = runner.invoke(app, ["instances", "get", "999"])
    assert result.exit_code == cli.EXIT_NOT_FOUND == 3
    assert "not found" in result.stderr


def test_validation_error_exits_4(runner: CliRunner, mock_client) -> None:
    _provoke(mock_client, ValidationError("bad input"))
    result = runner.invoke(app, ["instances", "list"])
    assert result.exit_code == cli.EXIT_VALIDATION == 4
    assert "invalid input" in result.stderr


def test_api_error_exits_5(runner: CliRunner, mock_client) -> None:
    err = APIError(status_code=500, message="boom")
    _provoke(mock_client, err)
    result = runner.invoke(app, ["instances", "list"])
    assert result.exit_code == cli.EXIT_API == 5
    assert "api error" in result.stderr
    assert "500" in result.stderr


def test_ssh_error_exits_7(runner: CliRunner, mock_client) -> None:
    _provoke(mock_client, SSHError("connection refused"))
    result = runner.invoke(app, ["instances", "list"])
    assert result.exit_code == cli.EXIT_SSH == 7
    assert "ssh error" in result.stderr


def test_generic_jarvislabs_error_exits_1(runner: CliRunner, mock_client) -> None:
    _provoke(mock_client, JarvislabsError("something else"))
    result = runner.invoke(app, ["instances", "list"])
    assert result.exit_code == cli.EXIT_GENERIC == 1
    assert "jarvislabs error" in result.stderr


def test_validation_error_required_gpu_type(runner: CliRunner, mock_client) -> None:
    """`instances create` with no gpu_type and no env default exits 4 before any API call."""
    result = runner.invoke(app, ["instances", "create"])
    assert result.exit_code == cli.EXIT_VALIDATION
    assert "--gpu-type" in result.stderr
    mock_client.instances.create.assert_not_called()
