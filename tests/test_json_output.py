"""Tests for the global --json output flag across read commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from jltool.cli import app

from .conftest import (
    fake_balance,
    fake_fs,
    fake_gpu,
    fake_instance,
    fake_key,
    fake_metrics,
    fake_script,
    fake_template,
)


def _parse(result_stdout: str):
    return json.loads(result_stdout)


def test_instances_list_json(runner: CliRunner, mock_client) -> None:
    mock_client.instances.list.return_value = [
        fake_instance(machine_id=1, name="alpha"),
        fake_instance(machine_id=2, name="beta"),
    ]
    result = runner.invoke(app, ["--json", "instances", "list"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 2
    assert {d["machine_id"] for d in data} == {1, 2}


def test_instances_list_json_filtered(runner: CliRunner, mock_client) -> None:
    mock_client.instances.list.return_value = [
        fake_instance(machine_id=1, status="Running"),
        fake_instance(machine_id=2, status="Paused"),
    ]
    result = runner.invoke(app, ["--json", "instances", "list", "--status", "Paused"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert len(data) == 1
    assert data[0]["machine_id"] == 2


def test_instances_get_json(runner: CliRunner, mock_client) -> None:
    mock_client.instances.get.return_value = fake_instance(machine_id=42, name="x")
    result = runner.invoke(app, ["--json", "instances", "get", "42"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert data["machine_id"] == 42
    assert data["name"] == "x"


def test_instances_create_json(runner: CliRunner, mock_client) -> None:
    mock_client.account.balance.return_value = fake_balance(balance=10.0)
    mock_client.instances.create.return_value = fake_instance(machine_id=99, name="boom")
    result = runner.invoke(
        app, ["--json", "instances", "create", "--gpu-type", "A100", "--no-preflight"]
    )
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert data["machine_id"] == 99


def test_instances_resume_json(runner: CliRunner, mock_client) -> None:
    mock_client.instances.resume.return_value = fake_instance(machine_id=5, status="Running")
    result = runner.invoke(app, ["--json", "instances", "resume", "5"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert data["machine_id"] == 5


def test_balance_json(runner: CliRunner, mock_client) -> None:
    mock_client.account.balance.return_value = fake_balance(balance=10.0, grants=2.0)
    mock_client.account.currency.return_value = "USD"
    result = runner.invoke(app, ["--json", "account", "balance"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert data["balance"] == 10.0
    assert data["grants"] == 2.0
    assert data["currency"] == "USD"


def test_metrics_json(runner: CliRunner, mock_client) -> None:
    mock_client.account.resource_metrics.return_value = fake_metrics(running_instances=3)
    result = runner.invoke(app, ["--json", "account", "metrics"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert data["running_instances"] == 3


def test_gpus_json(runner: CliRunner, mock_client) -> None:
    mock_client.account.gpu_availability.return_value = [
        fake_gpu(gpu_type="A100"),
        fake_gpu(gpu_type="H100"),
    ]
    result = runner.invoke(app, ["--json", "account", "gpus"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert {g["gpu_type"] for g in data} == {"A100", "H100"}


def test_gpus_cheapest_json(runner: CliRunner, mock_client) -> None:
    mock_client.account.gpu_availability.return_value = [
        fake_gpu(gpu_type="H100", num_free_devices=8, price_per_hour=2.99),
        fake_gpu(gpu_type="RTX5000", num_free_devices=6, price_per_hour=0.39),
    ]
    result = runner.invoke(app, ["--json", "account", "gpus", "--cheapest"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert len(data) == 1
    assert data[0]["gpu_type"] == "RTX5000"


def test_templates_json(runner: CliRunner, mock_client) -> None:
    mock_client.account.templates.return_value = [
        fake_template(id=1, title="PyTorch"),
        fake_template(id=2, title="TF"),
    ]
    result = runner.invoke(app, ["--json", "account", "templates"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert len(data) == 2


def test_scripts_list_json(runner: CliRunner, mock_client) -> None:
    mock_client.scripts.list.return_value = [fake_script(script_id=7, script_name="x")]
    result = runner.invoke(app, ["--json", "scripts", "list"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert data[0]["script_id"] == 7


def test_fs_list_json(runner: CliRunner, mock_client) -> None:
    mock_client.filesystems.list.return_value = [fake_fs(fs_id=3, fs_name="data", storage=200)]
    result = runner.invoke(app, ["--json", "fs", "list"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert data[0]["fs_id"] == 3


def test_keys_list_json(runner: CliRunner, mock_client) -> None:
    mock_client.ssh_keys.list.return_value = [fake_key(key_id=11, key_name="laptop")]
    result = runner.invoke(app, ["--json", "keys", "list"])
    assert result.exit_code == 0
    data = _parse(result.stdout)
    assert data[0]["key_id"] == 11
