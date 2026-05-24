# Sherlock Runner Gated

Preview:

```bash
python3 pistalab/pistalab.py sherlock-run pistalab/cases/<case_id>/case.json
```

Execution gate:

```bash
python3 pistalab/pistalab.py sherlock-run pistalab/cases/<case_id>/case.json \
  --execute \
  --confirm SHERLOCK_PUBLIC_ALIAS_CHECK
```

## What it does

- Loads `sherlock-plan`.
- Uses only allowed usernames from officially published aliases/name variants.
- Preview mode by default.
- Execution requires exact confirmation phrase.
- Blocks `--browse`.
- Saves raw stdout/stderr and weak-correlation ledger if Sherlock runs.

## What it does not do

- Does not contact accounts.
- Does not open profiles automatically.
- Does not treat username matches as proof.
- Does not submit tips.
- Does not search private phone/address/relatives.
