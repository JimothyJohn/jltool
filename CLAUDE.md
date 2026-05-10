# jarvislabs-tool — operator's manual

This file is the contract Claude Code (and any other agent) follows when
working in this repo. `jltool` is a CLI that gives **complete master control**
over Jarvislabs.ai infrastructure. It is the only sanctioned interface in this
project. Treat it as load-bearing infrastructure: it must be safe to drive
autonomously and easy to self-improve at a rapidly iterative scale.

---

## The master-control rule

**Never bypass `jltool`.** Every operation that touches Jarvislabs — creating
instances, pausing them, attaching filesystems, registering keys, checking
balance, listing GPUs — MUST go through `jltool`.

- Do not write `from jarvislabs import Client; ...` in scripts, notebooks, or
  ad-hoc Python. If you find yourself reaching for the SDK, the gap belongs in
  `jltool` instead — add the command, add the test, then use the command.
- Do not pipe through the Jarvislabs web dashboard for state changes when
  automating. Dashboard actions are invisible to the agent loop.
- Every public method on `client.{account,instances,scripts,filesystems,ssh_keys}`
  has a corresponding `jltool` subcommand. `tests/test_sdk_coverage.py` asserts
  this — if you add a new SDK method, the test will fail until you wire up the
  command.

When the SDK gains a new method, the workflow is:

1. Add a command to `jltool/cli.py`.
2. Add a test in `tests/test_<area>.py`.
3. Update the mapping in `tests/test_sdk_coverage.py`.
4. Run `pytest`. Commit only when green.

This is the self-improvement loop. Keep it tight.

---

## Command surface (every SDK method, mapped)

| Namespace | SDK method | jltool command |
|-----------|-----------|----------------|
| account | `balance` | `jltool account balance` (alias `jltool balance`) |
| account | `currency` | `jltool account currency` |
| account | `user_info` | `jltool account user-info` |
| account | `resource_metrics` | `jltool account metrics` |
| account | `gpu_availability` | `jltool account gpus` (`--gpu-type`, `--region`, `--cheapest`) |
| account | `templates` | `jltool account templates` |
| — | (constants) | `jltool account regions` |
| — | (composite) | `jltool account doctor` — auth + user + balance + metrics in one call |
| instances | `list` | `jltool instances list` (`--status`) (alias `jltool ls`) |
| instances | `get` | `jltool instances get <id>` |
| instances | `create` | `jltool instances create` (every SDK kwarg exposed as a flag) |
| instances | `pause` | `jltool instances pause <id>` |
| instances | `resume` | `jltool instances resume <id>` (every SDK kwarg as a flag) |
| instances | `destroy` | `jltool instances destroy <id> [-y]` |
| instances | `rename` | `jltool instances rename <id> <name>` |
| — | (helper) | `jltool instances ssh <id>` — print SSH command |
| — | (helper) | `jltool instances wait <id> --status Running --timeout 600` |
| — | (helper) | `jltool instances pause-all [-y]` |
| scripts | `list` | `jltool scripts list` |
| scripts | `add` | `jltool scripts add <name> -f <file>` |
| scripts | `update` | `jltool scripts update <id> -f <file>` |
| scripts | `remove` | `jltool scripts remove <id> [-y]` |
| filesystems | `list` | `jltool fs list` |
| filesystems | `create` | `jltool fs create <name> -s <gb> [--region] [--deployment-id]` |
| filesystems | `edit` | `jltool fs edit <id> -s <gb>` |
| filesystems | `remove` | `jltool fs remove <id> [-y]` |
| ssh_keys | `list` | `jltool keys list` |
| ssh_keys | `add` | `jltool keys add <name> [-f <file>]` |
| ssh_keys | `remove` | `jltool keys remove <id> [-y]` |

If you see an SDK method missing from this table, the table is wrong — fix it
and add the command.

---

## Contract for autonomous use

These properties are stable. Tests pin them. Agents can rely on them without
re-reading help text.

### JSON output

`jltool --json <subcommand>` switches every read command (and `instances
create`/`resume`/`wait`) to machine-readable JSON on stdout. Tables go to
stdout in human mode; warnings always go to stderr. Pipe `--json` output into
`jq` or parse it into structured tools.

```bash
jltool --json instances list --status Running | jq '.[].machine_id'
jltool --json account doctor
```

### Exit codes (stable contract)

| Code | Constant | Meaning |
|------|----------|---------|
| 0 | `EXIT_OK` | Success |
| 1 | `EXIT_GENERIC` | Unhandled `JarvislabsError`, or `instances wait` timeout |
| 2 | `EXIT_AUTH` | Missing / invalid API token |
| 3 | `EXIT_NOT_FOUND` | Resource (instance, script, fs, key) not found |
| 4 | `EXIT_VALIDATION` | Bad CLI input or `ValidationError` from the SDK |
| 5 | `EXIT_API` | Backend `APIError` (status code printed) |
| 6 | `EXIT_INSUFFICIENT_BALANCE` | Account balance cannot cover the operation |
| 7 | `EXIT_SSH` | SDK `SSHError` |

`jltool account doctor` exits **6** when balance is negative — branch on it
before any spend operation:

```bash
if jltool --json account doctor > /dev/null; then
    jltool instances create --gpu-type A100 --name worker
else
    echo "doctor failed — top up before launching" >&2
    exit 1
fi
```

### Defaults via .env

Every `instances create` parameter has a `JL_DEFAULT_*` env var counterpart
(see `.env.example`). Configure your fleet defaults once; commands stay short.
Per-call flags always override env defaults. `_env_int` warns and drops bad
values rather than crashing.

The CLI loads `.env` from CWD (then walks upward) **before** importing the
SDK, so `JL_API_KEY` resolves through `python-dotenv`. The `load_dotenv`
calls in `jltool/cli.py` must stay above `from jarvislabs import ...`.

### Confirmations

Destructive commands (`instances destroy`, `instances pause-all`, `scripts
remove`, `fs remove`, `keys remove`) prompt unless given `-y`/`--yes`. In
non-interactive contexts (agents, CI) always pass `-y`.

### Preflight balance check

`jltool instances create` calls `account.balance()` before the create and
warns to stderr if it's non-positive. The warning never blocks the create —
the SDK will reject with `InsufficientBalanceError` (exit 6) if it fails. To
skip the preflight (e.g. against fake clients in tests), pass `--no-preflight`.

### Polling with `instances wait`

`instances wait <id> --status Running --timeout 600 --interval 3` is the
canonical pattern for "create then use". It returns the freshly polled
instance (JSON when `--json`) on success and exits 1 on timeout. Default
timeout/interval mirror the SDK's `DEFAULT_POLL_TIMEOUT_S` / `POLL_INTERVAL_S`.

### A typical autonomous workflow

```bash
# 1. Fail fast on auth or balance.
jltool account doctor || exit $?

# 2. Pick the cheapest available GPU as JSON, parse it.
gpu=$(jltool --json account gpus --cheapest | jq -r '.[0].gpu_type')

# 3. Launch and capture the new machine_id.
mid=$(jltool --json instances create -g "$gpu" --name worker --no-preflight | jq '.machine_id')

# 4. Block until ready.
jltool instances wait "$mid" --status Running --timeout 900 || {
    jltool instances destroy "$mid" -y
    exit 1
}

# 5. Use it.
eval "$(jltool instances ssh "$mid")"

# 6. Tear down.
jltool instances destroy "$mid" -y
```

---

## Architecture (one-paragraph version)

Everything lives in `jltool/cli.py`. One root `typer.Typer` app, five sub-apps
mounted as command groups (`instances`, `scripts`, `fs`, `keys`, `account`),
plus two top-level shortcut commands (`ls`, `balance`). All SDK calls go
through the `jl_client()` context manager, which catches the SDK exception
hierarchy (`AuthError`, `InsufficientBalanceError`, `NotFoundError`,
`ValidationError`, `APIError`, `SSHError`, `JarvislabsError`) and translates
each to the distinct `typer.Exit` code listed above. Output uses two
`rich.console.Console` instances: `console` (stdout) and `err_console`
(stderr). The `_state` dataclass holds the global `--json` flag so commands
can switch their renderer. SDK response objects are accessed defensively with
`getattr(obj, "field", "-")` and the `_dump()` helper handles both pydantic
`model_dump()` and plain `vars()` cases.

When adding a command, wrap **only** the SDK call in `with jl_client() as
client:` — keep Rich rendering outside the `with` block so SDK errors surface
through the context manager rather than being masked by table-rendering
exceptions.

---

## Self-improvement loop

This project must be safe to evolve quickly. The loop is intentionally short:

1. **Read the failure.** A test failed, an exit code surprised you, an SDK
   method is missing — start with what's actually broken.
2. **Make the smallest change.** Add the flag, fix the handler, expand the env
   default. Don't refactor in the same change.
3. **Add a test.** Every behavior change needs a test before it counts as
   done. Use `tests/conftest.py`'s `mock_client` fixture — never hit the real
   API in tests.
4. **Run the suite.** `.venv/bin/pytest` — full run is under a second. There
   is no excuse not to run it.
5. **Verify live (read-only first).** `jltool account doctor`, `jltool ls`,
   `jltool --json account gpus` — these are safe and exercise the real auth
   path. Save destructive verification for the end.
6. **Commit.** Small commits. The commit message says *why*, not *what*.

### Project structure

```
jltool/
├── __init__.py      # version
└── cli.py           # entire CLI — single file by design, easy to grep
tests/
├── conftest.py            # mock_client fixture, Fake model bag, factories
├── test_smoke.py          # help text, --json flag wiring
├── test_errors.py         # SDK exception → exit code mapping
├── test_instances.py
├── test_scripts.py
├── test_filesystems.py
├── test_keys.py
├── test_account.py
├── test_env_defaults.py
├── test_json_output.py
└── test_sdk_coverage.py   # asserts every SDK method has a CLI command
```

`jltool/cli.py` is one file on purpose. When it gets unwieldy, split by
namespace — but only then.

### Adding a new command — checklist

- [ ] Function in `jltool/cli.py`, registered on the right sub-app.
- [ ] Every SDK keyword exposed as a flag with `Optional[...]` and `typer.Option`.
- [ ] Defaults pulled from `JL_DEFAULT_*` if it makes sense for the operation.
- [ ] `_state.json` branch that emits via `_print_json(_dump(...))`.
- [ ] Errors translated by the existing `jl_client()` context manager — don't
      add ad-hoc try/except.
- [ ] Test in `tests/test_<area>.py` covering happy path + at least one error.
- [ ] Entry in this CLAUDE.md command-surface table.
- [ ] If it's a new SDK method, update `tests/test_sdk_coverage.py`.

### What NOT to do

- Don't catch broad `Exception` outside `_preflight_balance`. Errors should
  flow through `jl_client()` and pick up the right exit code.
- Don't print operational chatter to stdout in `--json` mode — agents are
  parsing it. Warnings/preamble go to stderr.
- Don't add network calls inside the help/argument parsing path.
- Don't add a command without a test. The next agent will rely on it.
- Don't reach for the raw SDK in scripts when a `jltool` command can do the job.

---

## Setup

```bash
uv venv
uv pip install -e . --group dev
cp .env.example .env  # then edit JL_API_KEY
.venv/bin/pytest      # full suite, runs in <1s
.venv/bin/jltool account doctor
```

---

## Packaged as a Claude Code skill

The repo ships an on-demand skill at `.claude/skills/jarvislabs/`:

```
.claude/skills/jarvislabs/
├── SKILL.md          # frontmatter + concise trigger instructions
├── REFERENCE.md      # full command surface, every flag, exit codes
├── workflows.md      # autonomous-workflow recipe book
└── scripts/
    └── setup.sh      # idempotent installer + doctor preflight
```

Project-level: any Claude Code session opened in this repo auto-discovers
the skill from `.claude/skills/jarvislabs/SKILL.md`. No install needed.

User-level (use across all your projects):

```bash
mkdir -p ~/.claude/skills
ln -s "$(pwd)/.claude/skills/jarvislabs" ~/.claude/skills/jarvislabs
# or copy if you prefer a snapshot:
cp -r .claude/skills/jarvislabs ~/.claude/skills/jarvislabs
```

The skill description triggers on any mention of Jarvislabs.ai, GPU
instances, or `jltool`. When activated, Claude reads `SKILL.md`, then pulls
in `REFERENCE.md` or `workflows.md` on demand (progressive disclosure —
keeps SKILL.md under 200 lines).

`tests/test_skill_manifest.py` locks the manifest valid: frontmatter parses,
`name` is kebab-case + ≤64 chars, `description` ≤250 chars, every referenced
sibling file exists, `setup.sh` is executable + has the strict-mode pragma,
`REFERENCE.md` documents every namespace, and `workflows.md` includes the
doctor-preflight pattern. If a future change breaks any of these, the test
fails before the skill silently stops loading.

### Portability to other agent runtimes (e.g. OpenClaw)

The skill directory is intentionally vanilla: plain markdown files plus a
POSIX shell script. Nothing in the skill depends on Claude Code internals.
Any agent runtime that can:

1. Read a markdown file with YAML frontmatter as a system-prompt fragment, and
2. Execute bash commands,

can drop `.claude/skills/jarvislabs/` into its own skill directory and use it
as-is. The progressive-disclosure pattern (SKILL.md → REFERENCE.md →
workflows.md) is just file references; no special tooling required.

For OpenClaw or any other runtime, the integration shape is:

```python
# pseudocode for any agent runtime
skill = load_markdown_with_frontmatter(".claude/skills/jarvislabs/SKILL.md")
register_capability(
    name=skill.frontmatter["name"],
    description=skill.frontmatter["description"],
    body=skill.body,
    workdir=".claude/skills/jarvislabs",  # so ${CLAUDE_SKILL_DIR} resolves
)
```

The skill expects `${CLAUDE_SKILL_DIR}` to resolve to its own directory (so
references to `${CLAUDE_SKILL_DIR}/REFERENCE.md` work). If your runtime uses
a different variable, either set it before invoking the skill or do a
search-and-replace pass on load.
