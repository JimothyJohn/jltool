"""Tests for JL_DEFAULT_* environment variable merging in `instances create`."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from jltool import cli
from jltool.cli import app

from .conftest import fake_balance, fake_instance


def _stub_create(mock_client) -> None:
    mock_client.account.balance.return_value = fake_balance(balance=100.0)
    mock_client.instances.create.return_value = fake_instance()


def test_env_defaults_used_when_no_flags(
    runner: CliRunner, mock_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_create(mock_client)
    monkeypatch.setenv("JL_DEFAULT_GPU_TYPE", "L4")
    monkeypatch.setenv("JL_DEFAULT_NUM_GPUS", "2")
    monkeypatch.setenv("JL_DEFAULT_TEMPLATE", "tensorflow")
    monkeypatch.setenv("JL_DEFAULT_STORAGE", "100")
    monkeypatch.setenv("JL_DEFAULT_NAME", "from-env")
    monkeypatch.setenv("JL_DEFAULT_HTTP_PORTS", "7860")

    result = runner.invoke(app, ["instances", "create"])
    assert result.exit_code == 0, result.stderr
    mock_client.instances.create.assert_called_once_with(
        gpu_type="L4",
        num_gpus=2,
        template="tensorflow",
        storage=100,
        name="from-env",
        http_ports="7860",
    )


def test_cli_flags_override_env(
    runner: CliRunner, mock_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_create(mock_client)
    monkeypatch.setenv("JL_DEFAULT_GPU_TYPE", "L4")
    monkeypatch.setenv("JL_DEFAULT_NUM_GPUS", "2")

    result = runner.invoke(
        app, ["instances", "create", "--gpu-type", "H100", "--num-gpus", "4"]
    )
    assert result.exit_code == 0, result.stderr
    mock_client.instances.create.assert_called_once_with(gpu_type="H100", num_gpus=4)


def test_partial_env_partial_flags(
    runner: CliRunner, mock_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_create(mock_client)
    monkeypatch.setenv("JL_DEFAULT_TEMPLATE", "pytorch")
    monkeypatch.setenv("JL_DEFAULT_STORAGE", "40")

    result = runner.invoke(
        app, ["instances", "create", "--gpu-type", "A100", "--name", "x"]
    )
    assert result.exit_code == 0, result.stderr
    mock_client.instances.create.assert_called_once_with(
        gpu_type="A100", template="pytorch", storage=40, name="x"
    )


def test_invalid_int_env_warns_and_drops(
    runner: CliRunner, mock_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_create(mock_client)
    monkeypatch.setenv("JL_DEFAULT_NUM_GPUS", "not-a-number")

    result = runner.invoke(app, ["instances", "create", "--gpu-type", "A100"])
    assert result.exit_code == 0
    assert "JL_DEFAULT_NUM_GPUS" in result.stderr
    assert "ignoring" in result.stderr
    # The bad env value must not appear in the create call.
    args = mock_client.instances.create.call_args
    assert "num_gpus" not in args.kwargs


def test_empty_env_treated_as_unset(
    runner: CliRunner, mock_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_create(mock_client)
    monkeypatch.setenv("JL_DEFAULT_NAME", "")
    monkeypatch.setenv("JL_DEFAULT_REGION", "")

    result = runner.invoke(app, ["instances", "create", "--gpu-type", "A100"])
    assert result.exit_code == 0
    args = mock_client.instances.create.call_args
    assert "name" not in args.kwargs
    assert "region" not in args.kwargs


def test_missing_gpu_type_when_env_unset_fails_validation(
    runner: CliRunner, mock_client
) -> None:
    result = runner.invoke(app, ["instances", "create"])
    assert result.exit_code == cli.EXIT_VALIDATION
    mock_client.instances.create.assert_not_called()


def test_new_env_defaults_disk_script_args_arguments(
    runner: CliRunner, mock_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The env-default surface must cover every new SDK kwarg."""
    _stub_create(mock_client)
    monkeypatch.setenv("JL_DEFAULT_GPU_TYPE", "A100")
    monkeypatch.setenv("JL_DEFAULT_DISK_TYPE", "ssd")
    monkeypatch.setenv("JL_DEFAULT_SCRIPT_ARGS", "--epochs 5")
    monkeypatch.setenv("JL_DEFAULT_ARGUMENTS", "extra=foo")

    result = runner.invoke(app, ["instances", "create"])
    assert result.exit_code == 0, result.stderr
    mock_client.instances.create.assert_called_once_with(
        gpu_type="A100",
        disk_type="ssd",
        script_args="--epochs 5",
        arguments="extra=foo",
    )
