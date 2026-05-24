# Lead Hypothesis Worker

Command:

```bash
./PistaLab/pistalab hypotheses PistaLab/cases/<case_id>/case.json
```

Optional:

```bash
--ledger PistaLab/evidence/<case_id>/captures/evidence-ledger.jsonl
--score PistaLab/outputs/<case_id>/graph-score/confidence-score.json
--limit 3
```

## What it does

- Reads the case, evidence ledger, and graph confidence score.
- Generates lawful public-research hypotheses.
- Assigns priority scores.
- Produces allowed queries and blocked paths per hypothesis.
- Keeps hypotheses separate from accusations or tip submissions.

## What it does not do

- No external tip submission.
- No contact with people/entities.
- No doxxing searches.
- No sealed/private records.
- No leaked/private data.

## Output

```text
outputs/<case_id>/hypotheses/lead-hypotheses.json
outputs/<case_id>/hypotheses/lead-hypotheses.md
```

## Example output

Generated 5 hypotheses:

1. Official sources may list additional identifiers or reward program updates — 92.
2. Court docket can expose lawful shell-company/co-conspirator context — 88.
3. Aliases may connect to public articles/court docs/official notices — 74.
4. Public crypto scam reporting may reveal lawful network context — 70.
5. Non-official public articles should be cross-checked, not trusted — 58.

External actions performed: false.
