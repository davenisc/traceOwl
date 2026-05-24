# Court Records Deepening Worker

Command:

```bash
python3 pistalab/pistalab.py court-deepen pistalab/cases/<case_id>/case.json
```

Optional public search:

```bash
python3 pistalab/pistalab.py court-deepen pistalab/cases/<case_id>/case.json \
  --run-search \
  --max-queries 6 \
  --per-query 3
```

## What it does

- Extracts public court/legal clues from the case, source-check excerpt, and evidence ledger.
- Traces known official DOJ/court basis URLs.
- Generates safe court-record queries.
- Optionally runs only public/official search queries.
- Scores court depth separately from tip readiness.

## Blocked paths

- No sealed filings.
- No private database purchases.
- No contacting victims, witnesses, co-defendants, relatives, employers, or associates.
- No tip submission based only on court-context corroboration.

## Status meanings

- `DOCKET_PATH_READY`: public case number/docket path found.
- `CASE_CONTEXT_FOUND_NOT_DOCKET`: court context exists, but no case number yet.
- `COURT_CONTEXT_INCOMPLETE`: not enough public court context yet.
