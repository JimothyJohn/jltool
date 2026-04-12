"""Command-line interface for managing Jarvislabs.ai infrastructure."""

from __future__ import annotations

import json as _json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Load .env from CWD (and walk upwards) before importing the SDK so JL_API_KEY
# is available when the Client resolves credentials.
load_dotenv(Path.cwd() / ".env")
load_dotenv()

from jarvislabs import (  # noqa: E402
    APIError,
    AuthError,
    Client,
    InsufficientBalanceError,
    JarvislabsError,
    NotFoundError,
    SSHError,
    ValidationError,
)
from jarvislabs.client import (  # noqa: E402
    DEFAULT_POLL_TIMEOUT_S,
    EUROPE_GPU_COUNTS,
    EUROPE_GPU_TYPES,
    FILESYSTEM_REGIONS,
    POLL_INTERVAL_S,
    REGION_DISPLAY_CODES,
    REGION_PRIORITY,
    VM_SUPPORTED_REGIONS,
)

console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# State (reset between tests via the autouse fixture in tests/conftest.py)
# ---------------------------------------------------------------------------


@dataclass
class _State:
    json: bool = False


_state = _State()


# Exit codes — keep stable, tests assert against them.
EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_AUTH = 2
EXIT_NOT_FOUND = 3
EXIT_VALIDATION = 4
EXIT_API = 5
EXIT_INSUFFICIENT_BALANCE = 6
EXIT_SSH = 7


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


app = typer.Typer(
    name="jltool",
    help="Manage Jarvislabs.ai infrastructure (instances, scripts, filesystems, ssh keys).",
    no_args_is_help=True,
    add_completion=False,
)
instances_app = typer.Typer(help="Manage GPU instances.", no_args_is_help=True)
scripts_app = typer.Typer(help="Manage startup scripts.", no_args_is_help=True)
fs_app = typer.Typer(help="Manage persistent filesystems.", no_args_is_help=True)
keys_app = typer.Typer(help="Manage SSH keys.", no_args_is_help=True)
account_app = typer.Typer(help="Account, balance, GPU availability.", no_args_is_help=True)

app.add_typer(instances_app, name="instances")
app.add_typer(scripts_app, name="scripts")
app.add_typer(fs_app, name="fs")
app.add_typer(keys_app, name="keys")
app.add_typer(account_app, name="account")


@app.callback()
def main_callback(
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of human tables.",
    ),
) -> None:
    """jltool — manage Jarvislabs.ai infrastructure."""
    _state.json = json_out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env(key: str) -> Optional[str]:
    val = os.environ.get(key)
    return val if val not in (None, "") else None


def _env_int(key: str) -> Optional[int]:
    raw = _env(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        err_console.print(f"[yellow]warn:[/] {key}={raw!r} is not an int; ignoring")
        return None


def _dump(obj: Any) -> dict:
    """Best-effort conversion of an SDK model into a plain dict."""
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            return obj.model_dump()
        except Exception:
            pass
    try:
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    except TypeError:
        return {"value": str(obj)}


def _print_json(data: Any) -> None:
    """Render `data` as JSON to stdout (no Rich highlighting in pipes)."""
    typer.echo(_json.dumps(data, default=str, indent=2, sort_keys=True))


@contextmanager
def jl_client() -> Iterator[Client]:
    """Yield a Jarvislabs Client, translating SDK errors into clean exits."""
    try:
        with Client() as client:
            yield client
    except AuthError:
        err_console.print(
            "[red]auth error[/]: missing or invalid token. "
            "Set JL_API_KEY in your environment or .env, or run `jl setup`."
        )
        raise typer.Exit(EXIT_AUTH)
    except InsufficientBalanceError as exc:
        err_console.print(
            f"[red]insufficient balance[/]: {exc}\n"
            "  Top up at https://jarvislabs.ai/settings to continue."
        )
        raise typer.Exit(EXIT_INSUFFICIENT_BALANCE)
    except NotFoundError as exc:
        err_console.print(f"[red]not found[/]: {exc}")
        raise typer.Exit(EXIT_NOT_FOUND)
    except ValidationError as exc:
        err_console.print(f"[red]invalid input[/]: {exc}")
        raise typer.Exit(EXIT_VALIDATION)
    except APIError as exc:
        err_console.print(f"[red]api error[/] ({exc.status_code}): {exc.message}")
        raise typer.Exit(EXIT_API)
    except SSHError as exc:
        err_console.print(f"[red]ssh error[/]: {exc}")
        raise typer.Exit(EXIT_SSH)
    except JarvislabsError as exc:
        err_console.print(f"[red]jarvislabs error[/]: {exc}")
        raise typer.Exit(EXIT_GENERIC)


def _instance_row(inst: Any) -> tuple[str, ...]:
    return (
        str(getattr(inst, "machine_id", "-")),
        getattr(inst, "name", "-") or "-",
        getattr(inst, "status", "-") or "-",
        f"{getattr(inst, 'num_gpus', '-')}× {getattr(inst, 'gpu_type', '-')}",
        f"{getattr(inst, 'storage_gb', '-')} GB",
        getattr(inst, "template", "-") or "-",
        str(getattr(inst, "url", "") or ""),
    )


def _gpu_region(g: Any) -> str:
    """Pull the displayable region code from a GPU availability row."""
    try:
        return str(g.model_dump().get("region", "-"))
    except AttributeError:
        return str(getattr(g, "region", "-"))


# ---------------------------------------------------------------------------
# Top-level convenience commands
# ---------------------------------------------------------------------------


@app.command("ls")
def top_ls(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status."),
) -> None:
    """Shortcut for `jltool instances list`."""
    instances_list(status=status)


@app.command("balance")
def top_balance() -> None:
    """Shortcut for `jltool account balance`."""
    account_balance()


# ---------------------------------------------------------------------------
# instances
# ---------------------------------------------------------------------------


@instances_app.command("list")
def instances_list(
    status: Optional[str] = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter by status (Running, Paused, Creating, ...). Case-insensitive.",
    ),
) -> None:
    """List all instances on your account."""
    with jl_client() as client:
        items = client.instances.list()

    if status:
        items = [
            i for i in items
            if (getattr(i, "status", "") or "").lower() == status.lower()
        ]

    if _state.json:
        _print_json([_dump(i) for i in items])
        return

    if not items:
        console.print("[dim]No instances found.[/]")
        return

    table = Table(title="Jarvislabs Instances", show_lines=False)
    for col in ("ID", "Name", "Status", "GPU", "Storage", "Template", "URL"):
        table.add_column(col, overflow="fold")
    for inst in items:
        table.add_row(*_instance_row(inst))
    console.print(table)


@instances_app.command("get")
def instances_get(machine_id: int = typer.Argument(..., help="Instance machine_id")) -> None:
    """Show details for a single instance."""
    with jl_client() as client:
        inst = client.instances.get(machine_id)

    data = _dump(inst)

    if _state.json:
        _print_json(data)
        return

    table = Table(show_header=False, box=None)
    table.add_column("field", style="bold cyan")
    table.add_column("value", overflow="fold")
    for key, value in data.items():
        table.add_row(str(key), str(value))
    console.print(table)


@instances_app.command("ssh")
def instances_ssh(machine_id: int = typer.Argument(..., help="Instance machine_id")) -> None:
    """Print the SSH command for an instance to stdout (suitable for `eval $(...)`)."""
    with jl_client() as client:
        inst = client.instances.get(machine_id)
    cmd = getattr(inst, "ssh_command", None)
    if not cmd:
        err_console.print(f"[red]error[/]: instance {machine_id} has no ssh_command set")
        raise typer.Exit(EXIT_NOT_FOUND)
    typer.echo(cmd)


@instances_app.command("wait")
def instances_wait(
    machine_id: int = typer.Argument(..., help="Instance machine_id"),
    target: str = typer.Option(
        "Running", "--status", "-t", help="Status to wait for (case-insensitive)."
    ),
    timeout: int = typer.Option(
        DEFAULT_POLL_TIMEOUT_S, "--timeout", help="Maximum seconds to wait."
    ),
    interval: int = typer.Option(
        POLL_INTERVAL_S, "--interval", help="Poll interval in seconds."
    ),
) -> None:
    """Block until an instance reaches the target status (or timeout).

    Designed for autonomous workflows: chain after `instances create` to gate
    downstream work on the instance actually being ready.
    """
    deadline = time.monotonic() + timeout
    last_status: Optional[str] = None
    with jl_client() as client:
        while True:
            inst = client.instances.get(machine_id)
            current = (getattr(inst, "status", "") or "")
            if current.lower() == target.lower():
                if _state.json:
                    _print_json(_dump(inst))
                else:
                    console.print(f"[green]✓ {machine_id} is {current}[/]")
                return
            if current != last_status:
                if not _state.json:
                    console.print(f"[dim]  {machine_id} is {current}, waiting for {target}...[/]")
                last_status = current
            if time.monotonic() >= deadline:
                err_console.print(
                    f"[red]timeout[/]: instance {machine_id} still {current!r} after {timeout}s"
                )
                raise typer.Exit(EXIT_GENERIC)
            time.sleep(interval)


@instances_app.command("create")
def instances_create(
    gpu_type: Optional[str] = typer.Option(None, "--gpu-type", "-g", help="GPU model, e.g. A100, H100, L4"),
    num_gpus: Optional[int] = typer.Option(None, "--num-gpus", "-n", help="Number of GPUs"),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="Framework template (pytorch, tensorflow, vm, ...)"),
    storage: Optional[int] = typer.Option(None, "--storage", "-s", help="Disk size in GB"),
    name: Optional[str] = typer.Option(None, "--name", help="Instance name (max 40 chars)"),
    region: Optional[str] = typer.Option(None, "--region", help="Region (auto-selected if omitted)"),
    disk_type: Optional[str] = typer.Option(None, "--disk-type", help="Disk type, e.g. ssd"),
    script_id: Optional[str] = typer.Option(None, "--script-id", help="Startup script id to attach"),
    script_args: Optional[str] = typer.Option(None, "--script-args", help="Arguments passed to the startup script"),
    arguments: Optional[str] = typer.Option(None, "--arguments", help="Free-form arguments forwarded to the instance"),
    fs_id: Optional[int] = typer.Option(None, "--fs-id", help="Filesystem id to attach"),
    http_ports: Optional[str] = typer.Option(None, "--http-ports", help="Comma-separated ports, e.g. 7860,8080"),
    skip_preflight: bool = typer.Option(
        False,
        "--no-preflight",
        help="Skip the pre-create balance check.",
    ),
) -> None:
    """Create (and provision) a new instance.

    Every keyword argument exposed by `client.instances.create` is reachable as
    a flag here. Defaults are pulled from the JL_DEFAULT_* environment variables
    in your .env, so a fully configured .env makes `jltool instances create`
    a one-shot command.
    """
    payload: dict = {}
    payload["gpu_type"] = gpu_type or _env("JL_DEFAULT_GPU_TYPE")
    if not payload["gpu_type"]:
        err_console.print("[red]error[/]: --gpu-type is required (or set JL_DEFAULT_GPU_TYPE)")
        raise typer.Exit(EXIT_VALIDATION)

    for key, cli_val, env_val in (
        ("num_gpus", num_gpus, _env_int("JL_DEFAULT_NUM_GPUS")),
        ("template", template, _env("JL_DEFAULT_TEMPLATE")),
        ("storage", storage, _env_int("JL_DEFAULT_STORAGE")),
        ("name", name, _env("JL_DEFAULT_NAME")),
        ("region", region, _env("JL_DEFAULT_REGION")),
        ("disk_type", disk_type, _env("JL_DEFAULT_DISK_TYPE")),
        ("script_id", script_id, _env("JL_DEFAULT_SCRIPT_ID")),
        ("script_args", script_args, _env("JL_DEFAULT_SCRIPT_ARGS")),
        ("arguments", arguments, _env("JL_DEFAULT_ARGUMENTS")),
        ("fs_id", fs_id, _env_int("JL_DEFAULT_FS_ID")),
        ("http_ports", http_ports, _env("JL_DEFAULT_HTTP_PORTS")),
    ):
        chosen = cli_val if cli_val is not None else env_val
        if chosen is not None:
            payload[key] = chosen

    pretty = ", ".join(f"{k}={v}" for k, v in payload.items())
    if not _state.json:
        console.print(f"[dim]Creating instance:[/] {pretty}")

    with jl_client() as client:
        if not skip_preflight:
            _preflight_balance(client)
        inst = client.instances.create(**payload)

    if _state.json:
        _print_json(_dump(inst))
        return

    console.print(f"[green]✓ Created[/] machine_id={inst.machine_id} name={inst.name}")
    if getattr(inst, "ssh_command", None):
        console.print(f"  ssh: [cyan]{inst.ssh_command}[/]")
    if getattr(inst, "url", None):
        console.print(f"  url: [cyan]{inst.url}[/]")


def _preflight_balance(client: Any) -> None:
    """Warn (but never block) if account balance looks non-positive before create.

    Best-effort: any exception (network, schema mismatch, mocked test client)
    is swallowed because the user explicitly asked to create an instance.
    """
    try:
        bal = client.account.balance()
        bal_val = float(getattr(bal, "balance", 0) or 0)
    except Exception:  # noqa: BLE001 — preflight must never block create
        return
    if bal_val <= 0:
        err_console.print(
            f"[yellow]warning:[/] account balance is [red]{bal_val}[/] — "
            "create may fail with InsufficientBalance. "
            "Top up at https://jarvislabs.ai/settings."
        )


@instances_app.command("pause")
def instances_pause(machine_id: int = typer.Argument(...)) -> None:
    """Pause a running instance (stops compute billing, keeps data)."""
    with jl_client() as client:
        client.instances.pause(machine_id)
    console.print(f"[green]✓ Paused[/] {machine_id}")


@instances_app.command("resume")
def instances_resume(
    machine_id: int = typer.Argument(...),
    gpu_type: Optional[str] = typer.Option(None, "--gpu-type", "-g", help="Optionally switch GPU type"),
    num_gpus: Optional[int] = typer.Option(None, "--num-gpus", "-n", help="Optionally change GPU count"),
    storage: Optional[int] = typer.Option(None, "--storage", "-s", help="Optionally expand storage (GB)"),
    name: Optional[str] = typer.Option(None, "--name", help="Optionally rename"),
    http_ports: Optional[str] = typer.Option(None, "--http-ports", help="Comma-separated ports"),
    script_id: Optional[str] = typer.Option(None, "--script-id", help="Startup script id"),
    script_args: Optional[str] = typer.Option(None, "--script-args", help="Startup script arguments"),
    fs_id: Optional[int] = typer.Option(None, "--fs-id", help="Filesystem id to attach"),
) -> None:
    """Resume a paused instance. Hardware and attachments can be modified on resume."""
    kwargs: dict = {}
    for key, val in (
        ("gpu_type", gpu_type),
        ("num_gpus", num_gpus),
        ("storage", storage),
        ("name", name),
        ("http_ports", http_ports),
        ("script_id", script_id),
        ("script_args", script_args),
        ("fs_id", fs_id),
    ):
        if val is not None:
            kwargs[key] = val

    with jl_client() as client:
        inst = client.instances.resume(machine_id, **kwargs)

    if _state.json:
        _print_json(_dump(inst))
        return

    console.print(f"[green]✓ Resumed[/] machine_id={inst.machine_id} status={inst.status}")
    if getattr(inst, "url", None):
        console.print(f"  url: [cyan]{inst.url}[/]")


@instances_app.command("destroy")
def instances_destroy(
    machine_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Permanently destroy an instance. Attached filesystems are preserved."""
    if not yes:
        typer.confirm(
            f"Permanently destroy instance {machine_id}? This cannot be undone.",
            abort=True,
        )
    with jl_client() as client:
        client.instances.destroy(machine_id)
    console.print(f"[green]✓ Destroyed[/] {machine_id}")


@instances_app.command("rename")
def instances_rename(
    machine_id: int = typer.Argument(...),
    name: str = typer.Argument(..., help="New name (max 40 chars)"),
) -> None:
    """Rename an instance."""
    with jl_client() as client:
        client.instances.rename(machine_id, name)
    console.print(f"[green]✓ Renamed[/] {machine_id} -> {name}")


@instances_app.command("pause-all")
def instances_pause_all(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Pause every Running instance on the account."""
    with jl_client() as client:
        running = [i for i in client.instances.list() if getattr(i, "status", "") == "Running"]
        if not running:
            console.print("[dim]No running instances.[/]")
            return
        if not yes:
            ids = ", ".join(str(i.machine_id) for i in running)
            typer.confirm(f"Pause {len(running)} running instance(s): {ids}?", abort=True)
        for inst in running:
            client.instances.pause(inst.machine_id)
            console.print(f"  [green]paused[/] {inst.machine_id} ({inst.name})")


# ---------------------------------------------------------------------------
# scripts
# ---------------------------------------------------------------------------


@scripts_app.command("list")
def scripts_list() -> None:
    """List startup scripts."""
    with jl_client() as client:
        items = client.scripts.list()

    if _state.json:
        _print_json([_dump(s) for s in items])
        return

    if not items:
        console.print("[dim]No scripts.[/]")
        return
    table = Table(title="Startup Scripts")
    table.add_column("ID", style="bold")
    table.add_column("Name")
    for s in items:
        table.add_row(str(getattr(s, "script_id", "-")), getattr(s, "script_name", "-") or "-")
    console.print(table)


@scripts_app.command("add")
def scripts_add(
    name: str = typer.Argument(..., help="Script name"),
    file: Path = typer.Option(..., "--file", "-f", exists=True, readable=True, help="Path to a shell script"),
) -> None:
    """Upload a new startup script from a local file."""
    body = file.read_text()
    with jl_client() as client:
        client.scripts.add(script=body, name=name)
    console.print(f"[green]✓ Added[/] script {name!r} ({len(body)} bytes)")


@scripts_app.command("update")
def scripts_update(
    script_id: int = typer.Argument(...),
    file: Path = typer.Option(..., "--file", "-f", exists=True, readable=True),
) -> None:
    """Replace the body of an existing startup script."""
    body = file.read_text()
    with jl_client() as client:
        client.scripts.update(script_id=script_id, script=body)
    console.print(f"[green]✓ Updated[/] script {script_id}")


@scripts_app.command("remove")
def scripts_remove(
    script_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Delete a startup script."""
    if not yes:
        typer.confirm(f"Delete script {script_id}?", abort=True)
    with jl_client() as client:
        client.scripts.remove(script_id)
    console.print(f"[green]✓ Removed[/] script {script_id}")


# ---------------------------------------------------------------------------
# filesystems
# ---------------------------------------------------------------------------


@fs_app.command("list")
def fs_list() -> None:
    """List persistent filesystems."""
    with jl_client() as client:
        items = client.filesystems.list()

    if _state.json:
        _print_json([_dump(f) for f in items])
        return

    if not items:
        console.print("[dim]No filesystems.[/]")
        return
    table = Table(title="Filesystems")
    for col in ("ID", "Name", "Storage"):
        table.add_column(col)
    for f in items:
        table.add_row(
            str(getattr(f, "fs_id", "-")),
            getattr(f, "fs_name", "-") or "-",
            f"{getattr(f, 'storage', '-')} GB",
        )
    console.print(table)


@fs_app.command("create")
def fs_create(
    name: str = typer.Argument(..., help="Filesystem name"),
    storage: int = typer.Option(..., "--storage", "-s", help="Size in GB (50-2048)"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="Region (must be one supported by filesystems)"),
    deployment_id: Optional[str] = typer.Option(None, "--deployment-id", help="Bind the FS to a deployment"),
) -> None:
    """Create a new persistent filesystem."""
    kwargs: dict = {"fs_name": name, "storage": storage}
    if region is not None:
        kwargs["region"] = region
    if deployment_id is not None:
        kwargs["deployment_id"] = deployment_id
    with jl_client() as client:
        fs_id = client.filesystems.create(**kwargs)
    console.print(f"[green]✓ Created[/] filesystem id={fs_id} name={name} storage={storage}GB")


@fs_app.command("edit")
def fs_edit(
    fs_id: int = typer.Argument(...),
    storage: int = typer.Option(..., "--storage", "-s", help="New size in GB"),
) -> None:
    """Expand a filesystem."""
    with jl_client() as client:
        new_id = client.filesystems.edit(fs_id=fs_id, storage=storage)
    console.print(f"[green]✓ Resized[/] filesystem {fs_id} -> {new_id} ({storage}GB)")


@fs_app.command("remove")
def fs_remove(
    fs_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Delete a filesystem."""
    if not yes:
        typer.confirm(f"Delete filesystem {fs_id}? This cannot be undone.", abort=True)
    with jl_client() as client:
        client.filesystems.remove(fs_id)
    console.print(f"[green]✓ Removed[/] filesystem {fs_id}")


# ---------------------------------------------------------------------------
# ssh keys
# ---------------------------------------------------------------------------


@keys_app.command("list")
def keys_list() -> None:
    """List SSH keys registered on your account."""
    with jl_client() as client:
        items = client.ssh_keys.list()

    if _state.json:
        _print_json([_dump(k) for k in items])
        return

    if not items:
        console.print("[dim]No SSH keys.[/]")
        return
    table = Table(title="SSH Keys")
    for col in ("ID", "Name"):
        table.add_column(col)
    for k in items:
        table.add_row(str(getattr(k, "key_id", "-")), getattr(k, "key_name", "-") or "-")
    console.print(table)


@keys_app.command("add")
def keys_add(
    name: str = typer.Argument(..., help="Friendly key name"),
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="Public key file path (default: ~/.ssh/id_ed25519.pub)",
    ),
) -> None:
    """Register an SSH public key from a local file."""
    if file is None:
        file = Path.home() / ".ssh" / "id_ed25519.pub"
    if not file.exists():
        err_console.print(f"[red]error[/]: key file not found: {file}")
        raise typer.Exit(EXIT_VALIDATION)
    body = file.read_text().strip()
    if not body:
        err_console.print(f"[red]error[/]: key file is empty: {file}")
        raise typer.Exit(EXIT_VALIDATION)
    with jl_client() as client:
        client.ssh_keys.add(ssh_key=body, key_name=name)
    console.print(f"[green]✓ Added[/] key {name!r} from {file}")


@keys_app.command("remove")
def keys_remove(
    key_id: str = typer.Argument(..., help="Key ID (string per SDK signature)"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Delete an SSH key."""
    if not yes:
        typer.confirm(f"Remove SSH key {key_id}?", abort=True)
    with jl_client() as client:
        client.ssh_keys.remove(key_id)
    console.print(f"[green]✓ Removed[/] key {key_id}")


# ---------------------------------------------------------------------------
# account
# ---------------------------------------------------------------------------


@account_app.command("balance")
def account_balance() -> None:
    """Show account balance and credits."""
    with jl_client() as client:
        bal = client.account.balance()
        currency = client.account.currency()

    balance_val = getattr(bal, "balance", None)
    grants_val = getattr(bal, "grants", None)

    if _state.json:
        _print_json({"balance": balance_val, "grants": grants_val, "currency": currency})
        return

    try:
        is_negative = balance_val is not None and float(balance_val) < 0
    except (TypeError, ValueError):
        is_negative = False
    color = "red" if is_negative else "green"

    table = Table(show_header=False, box=None)
    table.add_column("field", style="bold cyan")
    table.add_column("value")
    table.add_row("balance", f"[{color}]{balance_val}[/] {currency}")
    if grants_val is not None:
        table.add_row("grants", str(grants_val))
    console.print(table)
    if is_negative:
        err_console.print(
            "[yellow]warning:[/] balance is negative — top up at https://jarvislabs.ai/settings"
        )


@account_app.command("metrics")
def account_metrics() -> None:
    """Show running/paused resource counts."""
    with jl_client() as client:
        m = client.account.resource_metrics()

    data = _dump(m)

    if _state.json:
        _print_json(data)
        return

    table = Table(show_header=False, box=None)
    table.add_column("metric", style="bold cyan")
    table.add_column("value")
    for k, v in data.items():
        table.add_row(str(k), str(v))
    console.print(table)


@account_app.command("gpus")
def account_gpus(
    gpu_type: Optional[str] = typer.Option(None, "--gpu-type", "-g", help="Filter by GPU type"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="Filter by region (IN1, IN2, EU1)"),
    cheapest: bool = typer.Option(
        False,
        "--cheapest",
        help="Show only the cheapest currently-available option.",
    ),
) -> None:
    """Show GPU availability and pricing across regions."""
    with jl_client() as client:
        gpus = client.account.gpu_availability()

    def matches(g: Any) -> bool:
        if gpu_type and (getattr(g, "gpu_type", "") or "").upper() != gpu_type.upper():
            return False
        if region and _gpu_region(g).upper() != region.upper():
            return False
        return True

    gpus = [g for g in gpus if matches(g)]

    if cheapest:
        available = [g for g in gpus if (getattr(g, "num_free_devices", 0) or 0) > 0]
        if not available:
            if _state.json:
                _print_json([])
            else:
                console.print("[dim]No available GPUs match.[/]")
            return
        gpus = [min(available, key=lambda g: float(getattr(g, "price_per_hour", 0) or 0))]

    if _state.json:
        _print_json([_dump(g) for g in gpus])
        return

    if not gpus:
        console.print("[dim]No GPU availability data.[/]")
        return

    table = Table(title="GPU Availability")
    for col in ("GPU", "Region", "Free", "Price/hr"):
        table.add_column(col)
    for g in gpus:
        free = getattr(g, "num_free_devices", 0) or 0
        free_str = f"[green]{free}[/]" if free > 0 else f"[red]{free}[/]"
        table.add_row(
            str(getattr(g, "gpu_type", "-")),
            _gpu_region(g),
            free_str,
            f"{getattr(g, 'price_per_hour', '-')}",
        )
    console.print(table)


@account_app.command("templates")
def account_templates() -> None:
    """List available framework templates."""
    with jl_client() as client:
        items = client.account.templates()

    if _state.json:
        _print_json([_dump(t) for t in items])
        return

    table = Table(title="Templates")
    for col in ("ID", "Title", "Category"):
        table.add_column(col)
    for t in items:
        table.add_row(
            str(getattr(t, "id", "-")),
            getattr(t, "title", "-") or "-",
            getattr(t, "category", "-") or "-",
        )
    console.print(table)


@account_app.command("user-info")
def account_user_info() -> None:
    """Show the authenticated user's profile (id, name, address, ...)."""
    with jl_client() as client:
        info = client.account.user_info()
    data = _dump(info)
    if _state.json:
        _print_json(data)
        return
    table = Table(show_header=False, box=None)
    table.add_column("field", style="bold cyan")
    table.add_column("value", overflow="fold")
    for key, value in data.items():
        table.add_row(str(key), str(value))
    console.print(table)


@account_app.command("currency")
def account_currency() -> None:
    """Show the account's billing currency (USD or INR)."""
    with jl_client() as client:
        currency = client.account.currency()
    if _state.json:
        _print_json({"currency": currency})
        return
    console.print(currency)


@account_app.command("regions")
def account_regions() -> None:
    """Show region constants exposed by the SDK (display codes, priority,
    filesystem-supported regions, VM-supported regions, Europe constraints)."""
    data = {
        "display_codes": dict(REGION_DISPLAY_CODES),
        "priority": list(REGION_PRIORITY),
        "filesystem_regions": sorted(FILESYSTEM_REGIONS),
        "vm_regions": sorted(VM_SUPPORTED_REGIONS),
        "europe_gpu_types": sorted(EUROPE_GPU_TYPES),
        "europe_gpu_counts": sorted(EUROPE_GPU_COUNTS),
    }
    if _state.json:
        _print_json(data)
        return
    table = Table(title="Jarvislabs Regions")
    table.add_column("Backend ID")
    table.add_column("Display")
    table.add_column("Filesystems")
    table.add_column("VM")
    for backend, display in REGION_DISPLAY_CODES.items():
        table.add_row(
            backend,
            display,
            "yes" if backend in FILESYSTEM_REGIONS else "no",
            "yes" if backend in VM_SUPPORTED_REGIONS else "no",
        )
    console.print(table)
    console.print(
        f"[dim]priority order:[/] {', '.join(REGION_PRIORITY)}"
    )
    console.print(
        f"[dim]europe constraints:[/] gpus={sorted(EUROPE_GPU_TYPES)} "
        f"counts={sorted(EUROPE_GPU_COUNTS)}"
    )


@account_app.command("doctor")
def account_doctor() -> None:
    """Run a one-shot health check: auth + user + balance + currency + metrics.

    Use this as the first step in autonomous workflows so the agent fails fast
    on bad credentials or insufficient balance before doing any real work.
    """
    with jl_client() as client:
        info = client.account.user_info()
        bal = client.account.balance()
        currency = client.account.currency()
        metrics = client.account.resource_metrics()

    balance_val = getattr(bal, "balance", None)
    grants_val = getattr(bal, "grants", None)
    try:
        is_negative = balance_val is not None and float(balance_val) < 0
    except (TypeError, ValueError):
        is_negative = False

    payload = {
        "ok": True,
        "user": _dump(info),
        "balance": balance_val,
        "grants": grants_val,
        "currency": currency,
        "balance_negative": is_negative,
        "metrics": _dump(metrics),
    }

    if _state.json:
        _print_json(payload)
        if is_negative:
            # Non-zero exit so agents can branch on doctor for "ready to spend".
            raise typer.Exit(EXIT_INSUFFICIENT_BALANCE)
        return

    color = "red" if is_negative else "green"
    table = Table(show_header=False, box=None, title="Jarvislabs Doctor")
    table.add_column("field", style="bold cyan")
    table.add_column("value")
    table.add_row("user_id", str(_dump(info).get("user_id", "-")))
    table.add_row("name", str(_dump(info).get("name", "-")))
    table.add_row("balance", f"[{color}]{balance_val}[/] {currency}")
    if grants_val is not None:
        table.add_row("grants", str(grants_val))
    for k, v in _dump(metrics).items():
        table.add_row(k, str(v))
    console.print(table)
    if is_negative:
        err_console.print(
            "[yellow]warning:[/] balance is negative — top up before creating instances."
        )
        raise typer.Exit(EXIT_INSUFFICIENT_BALANCE)


def main() -> None:  # pragma: no cover
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
