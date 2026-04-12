"""Lock in: every public method on every SDK namespace has a jltool command.

This is the load-bearing test for the master-control rule in CLAUDE.md.
If the SDK gains a new method and nobody wires it into jltool, this test
fails — the agent must add the command before merging.

The mapping is explicit (not introspected by name) so renames or grouped
commands stay obvious. To allow legitimate exceptions (an SDK method that
genuinely doesn't make sense as a CLI command), add it to ALLOWED_GAPS
with a justification — but the strong default is "no gaps".
"""

from __future__ import annotations

import inspect

import pytest

from jarvislabs.client import Account, Filesystems, Instances, Scripts, SSHKeys
from jltool.cli import app


# {sdk_method_qualified_name: jltool command path that exposes it}
SDK_TO_CLI = {
    # account
    "Account.balance": "account balance",
    "Account.currency": "account currency",
    "Account.user_info": "account user-info",
    "Account.resource_metrics": "account metrics",
    "Account.gpu_availability": "account gpus",
    "Account.templates": "account templates",
    # instances
    "Instances.list": "instances list",
    "Instances.get": "instances get",
    "Instances.create": "instances create",
    "Instances.pause": "instances pause",
    "Instances.resume": "instances resume",
    "Instances.destroy": "instances destroy",
    "Instances.rename": "instances rename",
    # scripts
    "Scripts.list": "scripts list",
    "Scripts.add": "scripts add",
    "Scripts.update": "scripts update",
    "Scripts.remove": "scripts remove",
    # filesystems
    "Filesystems.list": "fs list",
    "Filesystems.create": "fs create",
    "Filesystems.edit": "fs edit",
    "Filesystems.remove": "fs remove",
    # ssh keys
    "SSHKeys.list": "keys list",
    "SSHKeys.add": "keys add",
    "SSHKeys.remove": "keys remove",
}

# Genuinely-unsuitable SDK methods (none today). Add with a comment if needed.
ALLOWED_GAPS: set[str] = set()


def _public_methods(cls: type) -> list[str]:
    out = []
    for name, member in inspect.getmembers(cls, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        out.append(f"{cls.__name__}.{name}")
    return out


@pytest.mark.parametrize(
    "namespace",
    [Account, Instances, Scripts, Filesystems, SSHKeys],
    ids=lambda c: c.__name__,
)
def test_every_sdk_method_is_mapped(namespace: type) -> None:
    """For each SDK namespace, every public method must appear in SDK_TO_CLI
    (or be explicitly excused via ALLOWED_GAPS)."""
    methods = _public_methods(namespace)
    missing = [
        m for m in methods
        if m not in SDK_TO_CLI and m not in ALLOWED_GAPS
    ]
    assert not missing, (
        f"SDK methods missing from jltool: {missing}\n"
        "Add a command in jltool/cli.py and an entry in SDK_TO_CLI."
    )


def test_every_mapped_command_actually_exists() -> None:
    """Every command path in SDK_TO_CLI must resolve in the Typer app."""
    from typer.testing import CliRunner

    runner = CliRunner()
    for sdk_method, cmd_path in SDK_TO_CLI.items():
        # `--help` is the cheapest way to verify the command path is wired up.
        argv = cmd_path.split() + ["--help"]
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, (
            f"`jltool {cmd_path}` does not resolve "
            f"(needed for SDK method {sdk_method}). stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )


def test_helper_commands_present() -> None:
    """Composite/helper commands that don't map 1:1 to an SDK method but are
    documented as part of the master-control surface."""
    from typer.testing import CliRunner

    runner = CliRunner()
    for cmd in (
        ["account", "regions", "--help"],
        ["account", "doctor", "--help"],
        ["instances", "ssh", "--help"],
        ["instances", "wait", "--help"],
        ["instances", "pause-all", "--help"],
        ["ls", "--help"],
        ["balance", "--help"],
    ):
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0, f"missing helper: {cmd}"


def test_create_exposes_every_sdk_kwarg() -> None:
    """`instances create` must expose every keyword on the SDK signature as a flag."""
    from typer.testing import CliRunner

    sig = inspect.signature(Instances.create)
    sdk_kwargs = {
        name for name, p in sig.parameters.items()
        if p.kind == inspect.Parameter.KEYWORD_ONLY
    }

    runner = CliRunner()
    result = runner.invoke(app, ["instances", "create", "--help"])
    assert result.exit_code == 0
    help_text = result.stdout

    # Map SDK kwarg name -> expected CLI flag.
    flag_map = {
        "gpu_type": "--gpu-type",
        "num_gpus": "--num-gpus",
        "template": "--template",
        "storage": "--storage",
        "name": "--name",
        "disk_type": "--disk-type",
        "http_ports": "--http-ports",
        "script_id": "--script-id",
        "script_args": "--script-args",
        "fs_id": "--fs-id",
        "arguments": "--arguments",
        "region": "--region",
    }
    for kw in sdk_kwargs:
        flag = flag_map.get(kw)
        assert flag, f"new SDK kwarg `{kw}` on Instances.create — add a flag mapping"
        assert flag in help_text, f"`{flag}` missing from `instances create --help`"


def test_resume_exposes_every_sdk_kwarg() -> None:
    """`instances resume` must expose every keyword on the SDK signature as a flag."""
    from typer.testing import CliRunner

    sig = inspect.signature(Instances.resume)
    sdk_kwargs = {
        name for name, p in sig.parameters.items()
        if p.kind == inspect.Parameter.KEYWORD_ONLY
    }

    runner = CliRunner()
    result = runner.invoke(app, ["instances", "resume", "--help"])
    assert result.exit_code == 0
    help_text = result.stdout

    flag_map = {
        "gpu_type": "--gpu-type",
        "num_gpus": "--num-gpus",
        "storage": "--storage",
        "name": "--name",
        "http_ports": "--http-ports",
        "script_id": "--script-id",
        "script_args": "--script-args",
        "fs_id": "--fs-id",
    }
    for kw in sdk_kwargs:
        flag = flag_map.get(kw)
        assert flag, f"new SDK kwarg `{kw}` on Instances.resume — add a flag mapping"
        assert flag in help_text, f"`{flag}` missing from `instances resume --help`"
