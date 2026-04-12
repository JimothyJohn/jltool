<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/crucible-mark-dark.svg">
  <img src="docs/crucible-mark.svg" alt="Crucible" width="140">
</picture>

# CRUCIBLE

#### *A vessel for your compute.*

A precise command-line instrument for **[Jarvislabs.ai](https://jarvislabs.ai)** infrastructure.<br>
Stoke GPUs · tend filesystems · banish runaway bills — every operation a single verb.

<sub>[Install](#install) · [Configure](#configure) · [Commands](#commands) · [Exits](#exit-codes) · **[Webpage ↗](https://jimothyjohn.github.io/jarvislabs-tool/)**</sub>

</div>

---

```sh
$ jltool ls
$ jltool instances create -g A100 -n 1 -t pytorch -s 80 --name lab
$ jltool instances pause-all -y
```

Crucible wraps the official `jarvislabs` Python SDK behind a [Typer](https://typer.tiangolo.com/) CLI and exposes GPU instances, startup scripts, persistent filesystems, SSH keys, and account information as a single, predictable surface. The whole CLI lives in one file (`jltool/cli.py`) and ships as one console script (`jltool`).

## Install

Requires Python 3.10+.

```sh
git clone https://github.com/JimothyJohn/jarvislabs-tool.git
cd jarvislabs-tool
uv pip install -e .          # or: pip install -e .
```

The package installs a single console script: **`jltool`**.

## Configure

Crucible reads a `.env` file from the current directory (walking upward) **before** initializing the SDK. Copy the example and fill in your token:

```sh
cp .env.example .env
```

```env
# Required
JL_API_KEY=jl_xxxxxxxxxxxxxxxxxxxxxxxxx

# Defaults for `jltool instances create` — override per-call with the matching flag
JL_DEFAULT_GPU_TYPE=A100
JL_DEFAULT_NUM_GPUS=1
JL_DEFAULT_TEMPLATE=pytorch
JL_DEFAULT_STORAGE=40
JL_DEFAULT_NAME=
JL_DEFAULT_REGION=
JL_DEFAULT_HTTP_PORTS=
JL_DEFAULT_SCRIPT_ID=
JL_DEFAULT_FS_ID=
```

Get your API key at <https://jarvislabs.ai/settings/api-keys>.

## Commands

Run `jltool --help` for full reference. The CLI is organized into five groups plus two top-level shortcuts.

### `jltool instances` — GPU compute

| Command | Description |
| --- | --- |
| `list` | List every instance on the account |
| `get <id>` | Show details for a single instance |
| `create` | Create and provision a new instance (uses `JL_DEFAULT_*` for omitted flags) |
| `pause <id>` | Pause a running instance (stops compute billing, keeps data) |
| `resume <id>` | Resume a paused instance; hardware can be modified on resume |
| `rename <id> <name>` | Rename an instance (max 40 chars) |
| `destroy <id>` | Permanently destroy; attached filesystems are preserved |
| `pause-all` | Pause every running instance on the account |

### `jltool scripts` — startup scripts

| Command | Description |
| --- | --- |
| `list` | List startup scripts |
| `add <name> -f script.sh` | Upload a new script from a local file |
| `update <id> -f script.sh` | Replace the body of an existing script |
| `remove <id>` | Delete a script |

### `jltool fs` — persistent filesystems

| Command | Description |
| --- | --- |
| `list` | List filesystems |
| `create <name> -s <gb>` | Create a new filesystem (50–2048 GB) |
| `edit <id> -s <gb>` | Expand a filesystem |
| `remove <id>` | Delete a filesystem |

### `jltool keys` — SSH keys

| Command | Description |
| --- | --- |
| `list` | List registered SSH keys |
| `add <name> [-f key.pub]` | Register a public key (defaults to `~/.ssh/id_ed25519.pub`) |
| `remove <id>` | Delete a key |

### `jltool account` — billing & inventory

| Command | Description |
| --- | --- |
| `balance` | Show account balance and credits |
| `metrics` | Running and paused resource counts |
| `gpus` | GPU availability and pricing across regions |
| `templates` | List available framework templates |

### Top-level shortcuts

| Command | Equivalent |
| --- | --- |
| `jltool ls` | `jltool instances list` |
| `jltool balance` | `jltool account balance` |

## Examples

Provision an instance with all defaults from `.env`:

```sh
jltool instances create
```

Override on the fly:

```sh
jltool instances create --gpu-type H100 --num-gpus 2 --storage 200 --name train-run
```

Skip confirmation on destructive commands:

```sh
jltool instances destroy 48201 --yes
jltool instances pause-all -y
```

Attach a startup script and filesystem at create time:

```sh
jltool instances create --script-id 12 --fs-id 34 --http-ports 7860,8080
```

## Exit codes

Every SDK exception is translated to a distinct exit code so commands compose cleanly in shell scripts:

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Generic `JarvislabsError` |
| `2` | `AuthError` — missing or invalid token |
| `3` | `NotFoundError` — resource does not exist |
| `4` | `ValidationError` — invalid input |
| `5` | `APIError` — upstream failure (status code in stderr) |
| `130` | Interrupted (Ctrl-C) |

## Project layout

```
jltool/
  __init__.py
  cli.py              # the entire CLI lives here
docs/
  index.html          # GitHub Pages site
  crucible-mark.svg   # logomark (light theme)
  crucible-mark-dark.svg
pyproject.toml
.env.example
```

Built on [`jarvislabs`](https://pypi.org/project/jarvislabs/), [`typer`](https://typer.tiangolo.com/), [`rich`](https://rich.readthedocs.io/), and [`python-dotenv`](https://pypi.org/project/python-dotenv/).

## GitHub Pages

The webpage in `docs/` is a single self-contained HTML file with no build step. To publish:

1. Push to `main`.
2. In **Settings → Pages**, set **Source** to *Deploy from a branch*, **Branch** to `main`, **Folder** to `/docs`.
3. The site will appear at `https://<your-user>.github.io/jarvislabs-tool/`.

To preview locally: `python -m http.server -d docs 8000`, then open <http://localhost:8000>.
