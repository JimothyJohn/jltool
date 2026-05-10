# jltool — workflow recipes

Patterns for autonomous use. Each recipe is copy-pasteable and exits non-zero
on the first failure. Pair with `set -euo pipefail` in scripts.

## 1. Preflight every session

Always the first thing an agent does. One API call, exits 6 on negative
balance, exits 2 on bad auth.

```bash
jltool account doctor || {
    code=$?
    case $code in
      2) echo "set JL_API_KEY in .env, then re-run" >&2 ;;
      6) echo "balance is negative — top up at jarvislabs.ai/settings" >&2 ;;
      *) echo "doctor failed (exit $code)" >&2 ;;
    esac
    exit $code
}
```

## 2. Launch the cheapest available GPU and wait for it

```bash
gpu=$(jltool --json account gpus --cheapest | jq -r '.[0].gpu_type')
[ -n "$gpu" ] || { echo "no GPUs available" >&2; exit 1; }

mid=$(jltool --json instances create \
        --gpu-type "$gpu" \
        --name "agent-$(date +%s)" \
        --no-preflight \
      | jq '.machine_id')

jltool instances wait "$mid" --status Running --timeout 900 || {
    jltool instances destroy "$mid" -y
    exit 1
}

echo "ready: $(jltool instances ssh "$mid")"
```

## 3. Launch with a startup script and persistent filesystem

```bash
# Upload script (or reuse an existing one).
jltool scripts add bootstrap -f ./bootstrap.sh
script_id=$(jltool --json scripts list | jq -r '.[] | select(.script_name=="bootstrap") | .script_id')

# Create FS in a region that supports it.
fs_id=$(jltool --json fs create training-data -s 200 --region india-noida-01 \
        | jq '.fs_id // .')

# Launch.
jltool instances create \
    --gpu-type A100 \
    --region india-noida-01 \
    --script-id "$script_id" \
    --script-args "--epochs 10" \
    --fs-id "$fs_id" \
    --name training-run
```

## 4. Pause everything (cost guard)

```bash
# Lists then pauses every Running instance, no prompt.
jltool instances pause-all -y
jltool --json account metrics | jq '.running_instances'   # → 0
```

## 5. Filter and act on instances by status

```bash
# Destroy every Paused instance older than... well, every Paused instance.
jltool --json instances list --status Paused \
  | jq -r '.[].machine_id' \
  | xargs -I{} jltool instances destroy {} -y
```

## 6. Resume with hardware upgrade

```bash
# Resume instance 42 onto an H100 with more storage.
jltool instances resume 42 --gpu-type H100 --storage 200 --name upgraded
```

Note: machine_id may change after resume — capture the returned id.

```bash
new_id=$(jltool --json instances resume 42 --gpu-type H100 | jq '.machine_id')
```

## 7. SSH key bootstrap (required for VM template)

```bash
jltool keys list
# If empty:
jltool keys add laptop -f ~/.ssh/id_ed25519.pub
```

## 8. Find a specific instance by name

```bash
mid=$(jltool --json instances list \
      | jq '.[] | select(.name=="training-run") | .machine_id')
[ -n "$mid" ] || { echo "not found" >&2; exit 3; }
jltool instances get "$mid"
```

## 9. Check what's available in a region

```bash
jltool --json account gpus --region IN2 \
  | jq -r '.[] | "\(.gpu_type)\t\(.num_free_devices)\t$\(.price_per_hour)/hr"'
```

## 10. Doctor as a CI gate

```bash
# In a Makefile or GitHub Action — block downstream work on healthy account.
jltool --json account doctor > /tmp/doctor.json || exit $?
balance=$(jq '.balance' /tmp/doctor.json)
echo "balance=$balance" >> "$GITHUB_ENV"
```

## Anti-patterns (don't do these)

- **Don't `ssh` into an instance you just created without `instances wait`.**
  Provisioning takes seconds-to-minutes and the SSH endpoint isn't ready
  until status is Running.
- **Don't parse table output.** Tables are for humans. Always use `--json`
  when piping.
- **Don't leave instances running overnight by accident.** End every workflow
  with `instances destroy` or `instances pause`. Use `pause-all` as a
  panic button.
- **Don't catch and swallow exit codes.** They're the contract. If `doctor`
  exits 6, the agent should NOT proceed to `instances create`.
- **Don't write `from jarvislabs import Client` in any script.** Add the
  missing capability to `jltool` instead.
