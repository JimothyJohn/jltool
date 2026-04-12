"""Tests for the `jltool instances ...` subcommands."""

from __future__ import annotations

from typer.testing import CliRunner

from jltool import cli
from jltool.cli import app

from .conftest import fake_balance, fake_instance


# ---------------------------------------------------------------------------
# list / get / ssh
# ---------------------------------------------------------------------------


def test_list_renders_table(runner: CliRunner, mock_client) -> None:
    mock_client.instances.list.return_value = [
        fake_instance(machine_id=1, name="alpha", status="Running"),
        fake_instance(machine_id=2, name="beta", status="Paused"),
    ]
    result = runner.invoke(app, ["instances", "list"])
    assert result.exit_code == 0
    assert "alpha" in result.stdout
    assert "beta" in result.stdout
    assert "Running" in result.stdout


def test_list_empty(runner: CliRunner, mock_client) -> None:
    mock_client.instances.list.return_value = []
    result = runner.invoke(app, ["instances", "list"])
    assert result.exit_code == 0
    assert "No instances" in result.stdout


def test_list_status_filter_case_insensitive(runner: CliRunner, mock_client) -> None:
    mock_client.instances.list.return_value = [
        fake_instance(machine_id=1, name="alpha", status="Running"),
        fake_instance(machine_id=2, name="beta", status="Paused"),
    ]
    result = runner.invoke(app, ["instances", "list", "--status", "paused"])
    assert result.exit_code == 0
    assert "beta" in result.stdout
    assert "alpha" not in result.stdout


def test_list_status_filter_no_matches(runner: CliRunner, mock_client) -> None:
    mock_client.instances.list.return_value = [fake_instance(status="Running")]
    result = runner.invoke(app, ["instances", "list", "--status", "Paused"])
    assert result.exit_code == 0
    assert "No instances" in result.stdout


def test_get_renders_fields(runner: CliRunner, mock_client) -> None:
    mock_client.instances.get.return_value = fake_instance(machine_id=42, name="my-box")
    result = runner.invoke(app, ["instances", "get", "42"])
    assert result.exit_code == 0
    mock_client.instances.get.assert_called_once_with(42)
    assert "my-box" in result.stdout
    assert "machine_id" in result.stdout


def test_ssh_prints_command_only(runner: CliRunner, mock_client) -> None:
    mock_client.instances.get.return_value = fake_instance(
        machine_id=42, ssh_command="ssh -p 2222 root@10.0.0.1"
    )
    result = runner.invoke(app, ["instances", "ssh", "42"])
    assert result.exit_code == 0
    # stdout should contain exactly the ssh command (typer.echo adds newline)
    assert result.stdout.strip() == "ssh -p 2222 root@10.0.0.1"


def test_ssh_missing_command_errors(runner: CliRunner, mock_client) -> None:
    mock_client.instances.get.return_value = fake_instance(ssh_command=None)
    result = runner.invoke(app, ["instances", "ssh", "42"])
    assert result.exit_code == cli.EXIT_NOT_FOUND
    assert "no ssh_command" in result.stderr


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create_uses_explicit_flags(runner: CliRunner, mock_client) -> None:
    mock_client.account.balance.return_value = fake_balance(balance=100.0)
    mock_client.instances.create.return_value = fake_instance(machine_id=99, name="boom")
    result = runner.invoke(
        app,
        [
            "instances", "create",
            "--gpu-type", "H100",
            "--num-gpus", "2",
            "--template", "pytorch",
            "--storage", "80",
            "--name", "boom",
            "--http-ports", "7860,8080",
        ],
    )
    assert result.exit_code == 0, result.stderr
    mock_client.instances.create.assert_called_once_with(
        gpu_type="H100",
        num_gpus=2,
        template="pytorch",
        storage=80,
        name="boom",
        http_ports="7860,8080",
    )
    assert "Created" in result.stdout
    assert "machine_id=99" in result.stdout


def test_create_full_kwarg_surface(runner: CliRunner, mock_client) -> None:
    """Every SDK kwarg on Instances.create must be reachable from the CLI."""
    mock_client.instances.create.return_value = fake_instance()
    result = runner.invoke(
        app,
        [
            "instances", "create",
            "--gpu-type", "A100",
            "--num-gpus", "1",
            "--template", "pytorch",
            "--storage", "40",
            "--name", "x",
            "--region", "india-noida-01",
            "--disk-type", "ssd",
            "--script-id", "7",
            "--script-args", "--epochs 10",
            "--arguments", "extra=1",
            "--fs-id", "3",
            "--http-ports", "7860",
            "--no-preflight",
        ],
    )
    assert result.exit_code == 0, result.stderr
    mock_client.instances.create.assert_called_once_with(
        gpu_type="A100",
        num_gpus=1,
        template="pytorch",
        storage=40,
        name="x",
        region="india-noida-01",
        disk_type="ssd",
        script_id="7",
        script_args="--epochs 10",
        arguments="extra=1",
        fs_id=3,
        http_ports="7860",
    )


def test_create_preflight_warns_on_negative_balance(runner: CliRunner, mock_client) -> None:
    mock_client.account.balance.return_value = fake_balance(balance=-2.5)
    mock_client.instances.create.return_value = fake_instance()
    result = runner.invoke(app, ["instances", "create", "--gpu-type", "A100"])
    assert result.exit_code == 0
    assert "warning" in result.stderr
    assert "-2.5" in result.stderr
    # Create still attempted (warning, not block).
    mock_client.instances.create.assert_called_once()


def test_create_preflight_silent_on_failure(runner: CliRunner, mock_client) -> None:
    """Preflight failures must not block create."""
    mock_client.account.balance.side_effect = Exception("balance API down")
    mock_client.instances.create.return_value = fake_instance()
    result = runner.invoke(app, ["instances", "create", "--gpu-type", "A100"])
    assert result.exit_code == 0
    mock_client.instances.create.assert_called_once()


def test_create_skip_preflight_flag(runner: CliRunner, mock_client) -> None:
    mock_client.instances.create.return_value = fake_instance()
    result = runner.invoke(
        app, ["instances", "create", "--gpu-type", "A100", "--no-preflight"]
    )
    assert result.exit_code == 0
    mock_client.account.balance.assert_not_called()


# ---------------------------------------------------------------------------
# pause / resume / destroy / rename / pause-all
# ---------------------------------------------------------------------------


def test_pause(runner: CliRunner, mock_client) -> None:
    result = runner.invoke(app, ["instances", "pause", "5"])
    assert result.exit_code == 0
    mock_client.instances.pause.assert_called_once_with(5)
    assert "Paused" in result.stdout


def test_resume_no_overrides(runner: CliRunner, mock_client) -> None:
    mock_client.instances.resume.return_value = fake_instance(status="Running", url="http://x")
    result = runner.invoke(app, ["instances", "resume", "5"])
    assert result.exit_code == 0
    mock_client.instances.resume.assert_called_once_with(5)
    assert "Resumed" in result.stdout


def test_resume_with_overrides(runner: CliRunner, mock_client) -> None:
    mock_client.instances.resume.return_value = fake_instance()
    result = runner.invoke(
        app, ["instances", "resume", "5", "--gpu-type", "H100", "--storage", "200", "--name", "x"]
    )
    assert result.exit_code == 0
    mock_client.instances.resume.assert_called_once_with(
        5, gpu_type="H100", storage=200, name="x"
    )


def test_resume_full_kwarg_surface(runner: CliRunner, mock_client) -> None:
    """Every SDK kwarg on Instances.resume must be reachable from the CLI."""
    mock_client.instances.resume.return_value = fake_instance()
    result = runner.invoke(
        app,
        [
            "instances", "resume", "5",
            "--gpu-type", "H100",
            "--num-gpus", "2",
            "--storage", "200",
            "--name", "renamed",
            "--http-ports", "7860",
            "--script-id", "7",
            "--script-args", "--foo bar",
            "--fs-id", "3",
        ],
    )
    assert result.exit_code == 0, result.stderr
    mock_client.instances.resume.assert_called_once_with(
        5,
        gpu_type="H100",
        num_gpus=2,
        storage=200,
        name="renamed",
        http_ports="7860",
        script_id="7",
        script_args="--foo bar",
        fs_id=3,
    )


# ---------------------------------------------------------------------------
# wait
# ---------------------------------------------------------------------------


def test_wait_succeeds_after_polling(runner: CliRunner, mock_client, monkeypatch) -> None:
    # No actual sleeping during tests.
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)
    mock_client.instances.get.side_effect = [
        fake_instance(machine_id=42, status="Creating"),
        fake_instance(machine_id=42, status="Creating"),
        fake_instance(machine_id=42, status="Running"),
    ]
    result = runner.invoke(
        app, ["instances", "wait", "42", "--status", "Running", "--timeout", "60"]
    )
    assert result.exit_code == 0, result.stderr
    assert mock_client.instances.get.call_count == 3
    assert "Running" in result.stdout


def test_wait_target_case_insensitive(runner: CliRunner, mock_client, monkeypatch) -> None:
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)
    mock_client.instances.get.return_value = fake_instance(status="Running")
    result = runner.invoke(app, ["instances", "wait", "42", "--status", "running"])
    assert result.exit_code == 0


def test_wait_times_out(runner: CliRunner, mock_client, monkeypatch) -> None:
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)
    mock_client.instances.get.return_value = fake_instance(status="Creating")
    result = runner.invoke(
        app, ["instances", "wait", "42", "--status", "Running", "--timeout", "0"]
    )
    assert result.exit_code == cli.EXIT_GENERIC
    assert "timeout" in result.stderr
    assert "Creating" in result.stderr


def test_wait_json_emits_instance(runner: CliRunner, mock_client, monkeypatch) -> None:
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)
    mock_client.instances.get.return_value = fake_instance(machine_id=99, status="Running")
    result = runner.invoke(app, ["--json", "instances", "wait", "99"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.stdout)
    assert data["machine_id"] == 99
    assert data["status"] == "Running"


def test_destroy_aborts_without_yes(runner: CliRunner, mock_client) -> None:
    # Send "n" to the confirm prompt.
    result = runner.invoke(app, ["instances", "destroy", "5"], input="n\n")
    assert result.exit_code != 0
    mock_client.instances.destroy.assert_not_called()


def test_destroy_yes_flag_skips_prompt(runner: CliRunner, mock_client) -> None:
    result = runner.invoke(app, ["instances", "destroy", "5", "--yes"])
    assert result.exit_code == 0
    mock_client.instances.destroy.assert_called_once_with(5)
    assert "Destroyed" in result.stdout


def test_rename(runner: CliRunner, mock_client) -> None:
    result = runner.invoke(app, ["instances", "rename", "5", "newname"])
    assert result.exit_code == 0
    mock_client.instances.rename.assert_called_once_with(5, "newname")


def test_pause_all_no_running(runner: CliRunner, mock_client) -> None:
    mock_client.instances.list.return_value = [fake_instance(status="Paused")]
    result = runner.invoke(app, ["instances", "pause-all", "--yes"])
    assert result.exit_code == 0
    assert "No running" in result.stdout
    mock_client.instances.pause.assert_not_called()


def test_pause_all_with_yes(runner: CliRunner, mock_client) -> None:
    mock_client.instances.list.return_value = [
        fake_instance(machine_id=1, name="a", status="Running"),
        fake_instance(machine_id=2, name="b", status="Paused"),
        fake_instance(machine_id=3, name="c", status="Running"),
    ]
    result = runner.invoke(app, ["instances", "pause-all", "--yes"])
    assert result.exit_code == 0
    assert mock_client.instances.pause.call_count == 2
    paused_ids = sorted(c.args[0] for c in mock_client.instances.pause.call_args_list)
    assert paused_ids == [1, 3]


def test_pause_all_aborts_without_confirm(runner: CliRunner, mock_client) -> None:
    mock_client.instances.list.return_value = [fake_instance(status="Running")]
    result = runner.invoke(app, ["instances", "pause-all"], input="n\n")
    assert result.exit_code != 0
    mock_client.instances.pause.assert_not_called()


# ---------------------------------------------------------------------------
# top-level shortcuts
# ---------------------------------------------------------------------------


def test_top_ls_shortcut(runner: CliRunner, mock_client) -> None:
    mock_client.instances.list.return_value = [fake_instance(name="zeta")]
    result = runner.invoke(app, ["ls"])
    assert result.exit_code == 0
    assert "zeta" in result.stdout
