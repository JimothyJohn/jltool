"""Tests for the `jltool account ...` subcommands."""

from __future__ import annotations

from typer.testing import CliRunner

from jltool.cli import app

from jltool import cli

from .conftest import (
    fake_balance,
    fake_gpu,
    fake_metrics,
    fake_template,
    fake_user_info,
)


# ---------------------------------------------------------------------------
# balance
# ---------------------------------------------------------------------------


def test_balance_positive(runner: CliRunner, mock_client) -> None:
    mock_client.account.balance.return_value = fake_balance(balance=42.5, grants=5.0)
    mock_client.account.currency.return_value = "USD"
    result = runner.invoke(app, ["account", "balance"])
    assert result.exit_code == 0
    assert "42.5" in result.stdout
    assert "USD" in result.stdout
    # No warning on positive balance.
    assert "warning" not in result.stderr


def test_balance_negative_warns(runner: CliRunner, mock_client) -> None:
    mock_client.account.balance.return_value = fake_balance(balance=-2.62, grants=0.0)
    mock_client.account.currency.return_value = "USD"
    result = runner.invoke(app, ["account", "balance"])
    assert result.exit_code == 0
    assert "-2.62" in result.stdout
    assert "warning" in result.stderr
    assert "negative" in result.stderr


def test_top_balance_shortcut(runner: CliRunner, mock_client) -> None:
    mock_client.account.balance.return_value = fake_balance(balance=10.0)
    mock_client.account.currency.return_value = "USD"
    result = runner.invoke(app, ["balance"])
    assert result.exit_code == 0
    assert "10.0" in result.stdout


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def test_metrics(runner: CliRunner, mock_client) -> None:
    mock_client.account.resource_metrics.return_value = fake_metrics(
        running_instances=2, paused_instances=1, deployments=3
    )
    result = runner.invoke(app, ["account", "metrics"])
    assert result.exit_code == 0
    assert "running_instances" in result.stdout
    assert "2" in result.stdout
    assert "deployments" in result.stdout


# ---------------------------------------------------------------------------
# gpus
# ---------------------------------------------------------------------------


def test_gpus_renders(runner: CliRunner, mock_client) -> None:
    mock_client.account.gpu_availability.return_value = [
        fake_gpu(gpu_type="A100", region="IN2", num_free_devices=4, price_per_hour=1.29),
        fake_gpu(gpu_type="H100", region="EU1", num_free_devices=0, price_per_hour=2.99),
    ]
    result = runner.invoke(app, ["account", "gpus"])
    assert result.exit_code == 0
    assert "A100" in result.stdout
    assert "H100" in result.stdout
    assert "IN2" in result.stdout


def test_gpus_filter_by_type(runner: CliRunner, mock_client) -> None:
    mock_client.account.gpu_availability.return_value = [
        fake_gpu(gpu_type="A100", region="IN2"),
        fake_gpu(gpu_type="H100", region="EU1"),
    ]
    result = runner.invoke(app, ["account", "gpus", "--gpu-type", "h100"])
    assert result.exit_code == 0
    assert "H100" in result.stdout
    assert "A100" not in result.stdout


def test_gpus_filter_by_region(runner: CliRunner, mock_client) -> None:
    mock_client.account.gpu_availability.return_value = [
        fake_gpu(gpu_type="A100", region="IN2"),
        fake_gpu(gpu_type="H100", region="EU1"),
    ]
    result = runner.invoke(app, ["account", "gpus", "--region", "eu1"])
    assert result.exit_code == 0
    assert "H100" in result.stdout
    assert "A100" not in result.stdout


def test_gpus_cheapest_picks_min_price_among_available(runner: CliRunner, mock_client) -> None:
    mock_client.account.gpu_availability.return_value = [
        fake_gpu(gpu_type="H100", region="EU1", num_free_devices=8, price_per_hour=2.99),
        fake_gpu(gpu_type="RTX5000", region="IN1", num_free_devices=6, price_per_hour=0.39),
        fake_gpu(gpu_type="A6000", region="IN1", num_free_devices=8, price_per_hour=0.79),
        # Cheapest but unavailable — must be skipped.
        fake_gpu(gpu_type="L4", region="IN2", num_free_devices=0, price_per_hour=0.10),
    ]
    result = runner.invoke(app, ["account", "gpus", "--cheapest"])
    assert result.exit_code == 0
    assert "RTX5000" in result.stdout
    assert "H100" not in result.stdout
    assert "L4" not in result.stdout


def test_gpus_cheapest_no_match(runner: CliRunner, mock_client) -> None:
    mock_client.account.gpu_availability.return_value = [
        fake_gpu(gpu_type="L4", num_free_devices=0)
    ]
    result = runner.invoke(app, ["account", "gpus", "--cheapest"])
    assert result.exit_code == 0
    assert "No available GPUs" in result.stdout


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------


def test_templates(runner: CliRunner, mock_client) -> None:
    mock_client.account.templates.return_value = [
        fake_template(id=1, title="PyTorch", category="ML"),
        fake_template(id=2, title="TensorFlow", category="ML"),
    ]
    result = runner.invoke(app, ["account", "templates"])
    assert result.exit_code == 0
    assert "PyTorch" in result.stdout
    assert "TensorFlow" in result.stdout


# ---------------------------------------------------------------------------
# user-info / currency / regions / doctor
# ---------------------------------------------------------------------------


def test_user_info(runner: CliRunner, mock_client) -> None:
    mock_client.account.user_info.return_value = fake_user_info(
        user_id="u-42", name="Nick"
    )
    result = runner.invoke(app, ["account", "user-info"])
    assert result.exit_code == 0
    assert "u-42" in result.stdout
    assert "Nick" in result.stdout
    assert "user_id" in result.stdout


def test_user_info_json(runner: CliRunner, mock_client) -> None:
    mock_client.account.user_info.return_value = fake_user_info(user_id="u-42")
    result = runner.invoke(app, ["--json", "account", "user-info"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.stdout)
    assert data["user_id"] == "u-42"


def test_currency(runner: CliRunner, mock_client) -> None:
    mock_client.account.currency.return_value = "USD"
    result = runner.invoke(app, ["account", "currency"])
    assert result.exit_code == 0
    assert "USD" in result.stdout


def test_currency_json(runner: CliRunner, mock_client) -> None:
    mock_client.account.currency.return_value = "INR"
    result = runner.invoke(app, ["--json", "account", "currency"])
    assert result.exit_code == 0
    import json
    assert json.loads(result.stdout) == {"currency": "INR"}


def test_regions_table(runner: CliRunner) -> None:
    """`account regions` reads SDK constants — no client needed."""
    result = runner.invoke(app, ["account", "regions"])
    assert result.exit_code == 0
    # Display codes from REGION_DISPLAY_CODES.
    assert "IN1" in result.stdout
    assert "IN2" in result.stdout
    assert "EU1" in result.stdout


def test_regions_json(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--json", "account", "regions"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.stdout)
    assert "display_codes" in data
    assert "priority" in data
    assert "filesystem_regions" in data
    assert "vm_regions" in data
    # Check at least one expected mapping made it through.
    assert any("IN" in v or "EU" in v for v in data["display_codes"].values())


def test_doctor_happy_path(runner: CliRunner, mock_client) -> None:
    mock_client.account.user_info.return_value = fake_user_info(user_id="u-1", name="x")
    mock_client.account.balance.return_value = fake_balance(balance=42.0, grants=0.0)
    mock_client.account.currency.return_value = "USD"
    mock_client.account.resource_metrics.return_value = fake_metrics(running_instances=1)
    result = runner.invoke(app, ["account", "doctor"])
    assert result.exit_code == 0
    assert "u-1" in result.stdout
    assert "42.0" in result.stdout
    assert "running_instances" in result.stdout


def test_doctor_negative_balance_exits_6(runner: CliRunner, mock_client) -> None:
    """Doctor branches on balance: agents check exit 6 before any spend op."""
    mock_client.account.user_info.return_value = fake_user_info()
    mock_client.account.balance.return_value = fake_balance(balance=-2.62, grants=0.0)
    mock_client.account.currency.return_value = "USD"
    mock_client.account.resource_metrics.return_value = fake_metrics()
    result = runner.invoke(app, ["account", "doctor"])
    assert result.exit_code == cli.EXIT_INSUFFICIENT_BALANCE
    assert "warning" in result.stderr


def test_doctor_json_negative_balance(runner: CliRunner, mock_client) -> None:
    mock_client.account.user_info.return_value = fake_user_info()
    mock_client.account.balance.return_value = fake_balance(balance=-1.0)
    mock_client.account.currency.return_value = "USD"
    mock_client.account.resource_metrics.return_value = fake_metrics()
    result = runner.invoke(app, ["--json", "account", "doctor"])
    assert result.exit_code == cli.EXIT_INSUFFICIENT_BALANCE
    import json
    data = json.loads(result.stdout)
    assert data["balance_negative"] is True
    assert data["balance"] == -1.0


def test_doctor_json_happy(runner: CliRunner, mock_client) -> None:
    mock_client.account.user_info.return_value = fake_user_info(user_id="u-1")
    mock_client.account.balance.return_value = fake_balance(balance=10.0)
    mock_client.account.currency.return_value = "USD"
    mock_client.account.resource_metrics.return_value = fake_metrics()
    result = runner.invoke(app, ["--json", "account", "doctor"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["balance_negative"] is False
    assert data["user"]["user_id"] == "u-1"
