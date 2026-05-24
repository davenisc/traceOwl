# Evidence Capture Worker

Command:

```bash
./PistaLab/pistalab capture-evidence PistaLab/cases/<case_id>/case.json
```

Useful options:

```bash
--max-queries 6      # safety/throttle cap
--per-query 4        # result cap per query
--delay 0.4          # polite delay between queries
--fetch-pages        # optional: fetch public result pages and save redacted excerpts
--report-limit 10
```

## What it does

- Reads the case search plan.
- Runs only queries marked `allowed: true`.
- Skips blocked/doxxing-style queries.
- Uses public DuckDuckGo HTML search.
- Captures title, URL, domain, snippet, timestamp, URL hash, snippet hash, official-domain flag, and relevance score.
- Writes a local JSONL evidence ledger.
- Produces a Markdown summary of top results.

## What it does not do

- No external tip submission.
- No contact with people.
- No private/logged-in data.
- No hacking or bypassing access controls.
- No public accusations.

## Example run

Executed:

```bash
./PistaLab/pistalab capture-evidence \
  PistaLab/cases/sample-official-reward-notice/case.json \
  --max-queries 6 \
  --per-query 4 \
  --delay 0.4 \
  --report-limit 10
```

Generated:

```text
PistaLab/evidence/sample-official-reward-notice/captures/evidence-ledger.jsonl
PistaLab/evidence/sample-official-reward-notice/captures/capture-summary.json
PistaLab/evidence/sample-official-reward-notice/captures/capture-summary.md
```

Current result:

```text
queries_run: 6
results_captured: 7
errors: 0
external_actions_performed: false
```

Top public sources captured include State Department and Justice Department pages.
