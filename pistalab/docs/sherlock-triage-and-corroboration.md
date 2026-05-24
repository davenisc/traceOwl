# Sherlock Triage + Corroboration

## Triage

```bash
python3 pistalab/pistalab.py sherlock-triage pistalab/cases/<case_id>/case.json
```

- Converts raw Sherlock matches into corroboration priorities.
- Treats all Sherlock matches as weak correlation only.
- Prioritizes distinctive official aliases.
- Downgrades common/name-only usernames and low-value platforms.

## Corroboration

```bash
python3 pistalab/pistalab.py sherlock-corroborate pistalab/cases/<case_id>/case.json
```

- Uses search snippets only.
- Does not open profiles.
- Does not contact anyone.
- Looks for public connections between selected aliases and case facts.

## Policy

- No profile opening.
- No contact.
- No accusation.
- No tip submission from username matches alone.
