# Sherlock Username Correlation Worker

Tool candidate:

```text
https://github.com/sherlock-project/sherlock
```

Command:

```bash
python3 pistalab/pistalab.py sherlock-plan pistalab/cases/<case_id>/case.json
```

## What it does

- Generates a safe Sherlock plan from officially published aliases and primary-name variants.
- Blocks short/common aliases by default because false positives are likely.
- Writes command preview only.
- Does **not** run Sherlock.

## Policy

Sherlock matches are correlation leads only, never identity proof.

Blocked:

- no contact with discovered accounts,
- no accusations,
- no private phone/address/relatives searches,
- no `--browse` auto-opening/contact workflow,
- no tip submission based only on username matches.

## Output

```text
outputs/<case_id>/sherlock-plan/sherlock-plan.json
outputs/<case_id>/sherlock-plan/sherlock-plan.md
```
