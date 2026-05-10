---
name: jarvislabs
description: Use whenever Jarvislabs.ai infrastructure is involved — creating, listing, pausing, resuming, destroying GPU instances; managing startup scripts, persistent filesystems, SSH keys; checking balance or GPU availability via the jltool CLI.
allowed-tools: Bash Read Grep Glob
---

# jarvislabs

You are operating Jarvislabs.ai GPU infrastructure. The **only sanctioned
interface** is the `jltool` CLI. Never reach for `from jarvislabs import
Client` — if a capability is missing from `jltool`, treat that as a bug to
fix, not a reason to bypass it.

## Setup check (do this first)

Verify the CLI is installed and the API token is configured:

```bash
command -v jltool || bash ${CLAUDE_SKILL_DIR}/scripts/setup.sh
jltool account doctor
```

`account doctor` is a one-shot health check (auth + user + balance + currency
+ resource counts). It exits **6** when balance is non-positive, **2** on
auth failure. Branch on its exit code before any spend operation.

## Stable contracts you can rely on

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Generic JarvislabsError, or `instances wait` timeout |
| 2 | Missing / invalid API token |
| 3 | Resource not found |
| 4 | Bad input or SDK ValidationError |
| 5 | Backend APIError (status code printed) |
| 6 | Insufficient balance |
| 7 | SSHError |

### `--json` output

`jltool --json <subcommand>` switches every read command (and `instances
create`/`resume`/`wait`) to machine-readable JSON on stdout. Tables are for
humans, JSON is for you. Pipe into `jq`. Warnings always go to stderr — never
mix them with the parseable output.

```bash
jltool --json instances list --status Running | jq -r '.[].machine_id'
jltool --json account gpus --cheapest | jq -r '.[0].gpu_type'
```

### `JL_DEFAULT_*` env defaults

Every parameter on `instances create` has a `JL_DEFAULT_*` env var
counterpart. Per-call flags override env. Configure fleet defaults once in
`.env`; commands stay short.

### Confirmations

Destructive commands (`instances destroy`, `instances pause-all`, `scripts
remove`, `fs remove`, `keys remove`) prompt unless given `-y`/`--yes`.
Always pass `-y` in non-interactive flows.

## Canonical autonomous workflow

```bash
# 1. Fail fast on auth or balance.
jltool account doctor || exit $?

# 2. Pick the cheapest available GPU as JSON.
gpu=$(jltool --json account gpus --cheapest | jq -r '.[0].gpu_type')

# 3. Launch and capture the new machine_id.
mid=$(jltool --json instances create -g "$gpu" --name worker --no-preflight \
        | jq '.machine_id')

# 4. Block until ready.
jltool instances wait "$mid" --status Running --timeout 900 || {
    jltool instances destroy "$mid" -y
    exit 1
}

# 5. Use it.
eval "$(jltool instances ssh "$mid")"

# 6. Tear down when done — never leave instances running.
jltool instances destroy "$mid" -y
```

## When you need more

- **Full command surface, every flag, every namespace** — read
  `${CLAUDE_SKILL_DIR}/REFERENCE.md`.
- **Recipe book for common multi-step workflows** — read
  `${CLAUDE_SKILL_DIR}/workflows.md`.
- **First-time install or token setup** — run
  `bash ${CLAUDE_SKILL_DIR}/scripts/setup.sh`.

## Operating principles

1. **Always run `jltool account doctor` before spend operations.** It costs
   one API call and saves agents from launching into a -$2 balance.
2. **Always tear down what you created.** Use `instances destroy` (or
   `instances pause` if you'll resume soon — pause keeps storage cost only).
   Idle GPUs cost real money.
3. **Use `--json` whenever piping into another command or parsing.** Tables
   are unstable; JSON is the contract.
4. **Use `instances wait` between create and use.** Don't `ssh` into a
   provisioning instance — it'll fail or worse, hang.
5. **If a command you need doesn't exist, add it.** The repo at the project
   root has `jltool/cli.py` (single file) and `tests/` (mocked SDK fixtures).
   Add the flag, add the test, run `pytest`, commit. The
   `tests/test_sdk_coverage.py` test asserts every SDK method has a CLI
   command — keep it green.
