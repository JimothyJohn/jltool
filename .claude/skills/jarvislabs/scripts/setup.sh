#!/usr/bin/env bash
# Bootstraps `jltool` if it isn't already on PATH, then verifies auth.
#
# Strategy:
#   1. If `jltool` is already callable, exit 0 with a noop.
#   2. If we're inside (or near) the jarvislabs-tool repo, install editable
#      via uv into a local .venv.
#   3. Otherwise instruct the user to clone the repo. (PyPI publish TBD.)
#
# Safe to run repeatedly — each step is idempotent.
set -euo pipefail

log() { printf '[jarvislabs-skill] %s\n' "$*" >&2; }

JLTOOL_BIN=""

if command -v jltool >/dev/null 2>&1; then
    JLTOOL_BIN="$(command -v jltool)"
    log "jltool already on PATH ($JLTOOL_BIN)"
else
    # Find the repo root: walk up from CWD looking for jltool/cli.py.
    repo=""
    dir="$(pwd)"
    while [ "$dir" != "/" ]; do
        if [ -f "$dir/jltool/cli.py" ] && [ -f "$dir/pyproject.toml" ]; then
            repo="$dir"
            break
        fi
        dir="$(dirname "$dir")"
    done

    if [ -z "$repo" ]; then
        cat >&2 <<'EOF'
[jarvislabs-skill] jltool is not installed and the source repo could not be
found by walking up from $(pwd). To install:

  git clone https://github.com/JimothyJohn/jarvislabs-tool ~/src/jarvislabs-tool
  cd ~/src/jarvislabs-tool
  uv venv && uv pip install -e .
  ln -s "$(pwd)/.venv/bin/jltool" ~/.local/bin/jltool   # or add to PATH

Then re-run this skill.
EOF
        exit 1
    fi

    log "found jarvislabs-tool source at $repo — installing editable"

    if ! command -v uv >/dev/null 2>&1; then
        log "uv is required (https://docs.astral.sh/uv/) — please install it first"
        exit 1
    fi

    (
        cd "$repo"
        [ -d .venv ] || uv venv
        uv pip install -e . >/dev/null
    )

    JLTOOL_BIN="$repo/.venv/bin/jltool"
    if [ -x "$JLTOOL_BIN" ]; then
        log "installed: $JLTOOL_BIN"
        log "tip: add '$repo/.venv/bin' to PATH or symlink jltool into ~/.local/bin"
    else
        log "install completed but jltool binary not found at $JLTOOL_BIN"
        exit 1
    fi
fi

# --- Token check ---------------------------------------------------------

if [ -z "${JL_API_KEY:-}" ]; then
    # Try loading .env from CWD (the CLI does this too, but the doctor call
    # below depends on it being present in the env at this layer).
    if [ -f .env ]; then
        # shellcheck disable=SC1091
        set -a; . ./.env; set +a
    fi
fi

if [ -z "${JL_API_KEY:-}" ]; then
    cat >&2 <<'EOF'
[jarvislabs-skill] JL_API_KEY is not set. Either:
  1. Add JL_API_KEY=<token> to .env in your project, or
  2. export JL_API_KEY=<token> in your shell.

Get a token at https://jarvislabs.ai/settings/api-keys
EOF
    exit 2
fi

log "JL_API_KEY is set — running doctor"
exec "$JLTOOL_BIN" account doctor
