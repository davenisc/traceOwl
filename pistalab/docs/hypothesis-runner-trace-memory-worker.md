# Hypothesis Runner + Trace Memory Worker

Command:

```bash
./PistaLab/pistalab run-hypotheses PistaLab/cases/<case_id>/case.json --refresh
```

Useful options:

```bash
--top 2
--hypothesis-id <id>
--max-queries-per-hypothesis 3
--per-query 4
--max-basis-per-hypothesis 3
--fetch-pages
--trace-id <custom-id>
```

## What it does

- Selects top hypotheses or one specified hypothesis.
- Traces each hypothesis evidence basis into a reproducible trace ledger.
- Runs only allowed hypothesis queries.
- Skips blocked paths.
- Writes per-run trace artifacts.
- Updates durable case memory.
- Runs lead-trace analysis.
- With `--refresh`, updates graph score and refreshed hypotheses from the expanded ledger.

## Memory

Writes:

```text
PistaLab/cases/<case_id>/case-memory.json
```

The memory stores:

- run timestamp,
- trace id,
- hypotheses run,
- queries run,
- results captured,
- lead-analysis status,
- external action flag.

## Trace analysis

Writes:

```text
PistaLab/evidence/<case_id>/traces/<trace_id>/trace-ledger.jsonl
PistaLab/evidence/<case_id>/traces/<trace_id>/lead-trace-analysis.json
PistaLab/evidence/<case_id>/traces/<trace_id>/lead-trace-analysis.md
```

`new_lead_status` values:

- `NO_RESULTS`
- `NO_NEW_ACTIONABLE_LEAD`
- `POTENTIAL_RESEARCH_LEAD`
- `POTENTIAL_ALIAS_LEAD`

## Example latest trace

Latest run:

```text
hypotheses_run: 2
queries_run: 6
results_captured: 6
new_lead_status: NO_NEW_ACTIONABLE_LEAD
external_actions_performed: false
```

Interpretation: the top official/court-record routes added traceable corroboration from official basis URLs, but no new actionable tip was found yet.
