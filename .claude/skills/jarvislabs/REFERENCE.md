# jltool — full command reference

This is the deep reference. For "when to use this skill at all" see
`SKILL.md`. For workflow recipes see `workflows.md`.

## Top-level

```
jltool [--json] <command>
```

`--json` is a global flag that must come BEFORE the subcommand. It switches
every read command (and `instances create`/`resume`/`wait`) to JSON on
stdout. Without it, commands render Rich tables.

Top-level shortcuts:
- `jltool ls` → `jltool instances list`
- `jltool balance` → `jltool account balance`

## account

| Command | What it does |
|---------|--------------|
| `account balance` | Current balance + grants. Negative balance prints a stderr warning. |
| `account currency` | Billing currency (USD or INR). |
| `account user-info` | User profile (id, name, address, ...). |
| `account metrics` | Resource counts (running/paused instances, vms, deployments, filesystems). |
| `account gpus` | GPU availability across regions. Flags: `--gpu-type`, `--region`, `--cheapest`. |
| `account templates` | Available framework templates. |
| `account regions` | Region constants from the SDK (display codes, priority, fs/vm support, EU constraints). No API call. |
| `account doctor` | One-shot health check: auth + user + balance + currency + metrics. **Exits 6 on negative balance** — branch on this for autonomous workflows. |

## instances

### Read

| Command | Notes |
|---------|-------|
| `instances list [--status STATUS]` | Case-insensitive status filter. |
| `instances get <machine_id>` | All fields on the instance. |
| `instances ssh <machine_id>` | Prints `ssh_command` to stdout (suitable for `eval $(...)`). |

### Create / modify

`instances create` exposes every kwarg on the SDK's `Instances.create`:

| Flag | SDK kwarg | Env default |
|------|-----------|-------------|
| `--gpu-type` / `-g` (required) | `gpu_type` | `JL_DEFAULT_GPU_TYPE` |
| `--num-gpus` / `-n` | `num_gpus` | `JL_DEFAULT_NUM_GPUS` |
| `--template` / `-t` | `template` | `JL_DEFAULT_TEMPLATE` |
| `--storage` / `-s` | `storage` | `JL_DEFAULT_STORAGE` |
| `--name` | `name` | `JL_DEFAULT_NAME` |
| `--region` | `region` | `JL_DEFAULT_REGION` |
| `--disk-type` | `disk_type` | `JL_DEFAULT_DISK_TYPE` |
| `--script-id` | `script_id` | `JL_DEFAULT_SCRIPT_ID` |
| `--script-args` | `script_args` | `JL_DEFAULT_SCRIPT_ARGS` |
| `--arguments` | `arguments` | `JL_DEFAULT_ARGUMENTS` |
| `--fs-id` | `fs_id` | `JL_DEFAULT_FS_ID` |
| `--http-ports` | `http_ports` | `JL_DEFAULT_HTTP_PORTS` |
| `--no-preflight` | (skip pre-create balance check) | — |

`instances resume <id>` exposes every resume kwarg:

| Flag | SDK kwarg |
|------|-----------|
| `--gpu-type` / `-g` | `gpu_type` |
| `--num-gpus` / `-n` | `num_gpus` |
| `--storage` / `-s` | `storage` |
| `--name` | `name` |
| `--http-ports` | `http_ports` |
| `--script-id` | `script_id` |
| `--script-args` | `script_args` |
| `--fs-id` | `fs_id` |

### Lifecycle

| Command | Notes |
|---------|-------|
| `instances pause <id>` | Stops compute billing, keeps data. |
| `instances destroy <id> [-y]` | Permanent. Filesystems persist. Prompts unless `-y`. |
| `instances rename <id> <name>` | Max 40 chars. |
| `instances pause-all [-y]` | Pauses every Running instance. Prompts unless `-y`. |
| `instances wait <id> [--status Running] [--timeout 600] [--interval 3]` | Polls until target status. Exits 1 on timeout. Defaults match SDK constants. |

## scripts

| Command | Notes |
|---------|-------|
| `scripts list` | All startup scripts. |
| `scripts add <name> -f <file>` | Upload a shell script from disk. |
| `scripts update <id> -f <file>` | Replace body. |
| `scripts remove <id> [-y]` | Delete. |

## fs (filesystems)

| Command | Notes |
|---------|-------|
| `fs list` | All persistent filesystems. |
| `fs create <name> -s <gb> [--region R] [--deployment-id D]` | 50–2048 GB. Region must be in the FS-supported set (see `account regions`). |
| `fs edit <id> -s <gb>` | Expand. |
| `fs remove <id> [-y]` | Delete. |

## keys (SSH keys)

| Command | Notes |
|---------|-------|
| `keys list` | All registered SSH keys. |
| `keys add <name> [-f <file>]` | Default file: `~/.ssh/id_ed25519.pub`. |
| `keys remove <id> [-y]` | `id` is a string per the SDK. |

## Region cheat sheet

`account regions` is the source of truth, but for quick reference:

- `IN1` = `india-01` — RTX5000, A5000Pro, A6000, RTX6000Ada, A100. Filesystems yes, VMs no.
- `IN2` = `india-noida-01` — L4, A100, A100-80GB. Filesystems yes, VMs yes.
- `EU1` = `europe-01` — H100, H200 (1 or 8 GPUs only). Filesystems no, VMs yes.

VM template requires at least one SSH key registered AND a region in
`{IN2, EU1}`. EU1 needs ≥100 GB storage.

## Stable exit codes

| Code | Constant | Meaning |
|------|----------|---------|
| 0 | EXIT_OK | Success |
| 1 | EXIT_GENERIC | Unhandled JarvislabsError or `wait` timeout |
| 2 | EXIT_AUTH | Missing / invalid API token |
| 3 | EXIT_NOT_FOUND | Resource not found |
| 4 | EXIT_VALIDATION | Bad CLI input or ValidationError |
| 5 | EXIT_API | Backend APIError (status code printed) |
| 6 | EXIT_INSUFFICIENT_BALANCE | Account balance non-positive |
| 7 | EXIT_SSH | SDK SSHError |
