# PistaLab for traceOwl

PistaLab is a compliance-first reward-intelligence / public OSINT module for traceOwl.

It turns official public reward notices into structured cases, verifies official sources, captures lawful public evidence, builds entity graphs, scores research confidence, generates lead hypotheses, traces research runs, stores case memory, and drafts review-only tip packets.

## What this is

A lawful public-source intelligence workflow for official reward/tip notices.

It is designed for:

- official reward notice intake,
- source legitimacy checks,
- public evidence capture,
- entity graph + confidence scoring,
- lead hypothesis generation,
- traceable research memory,
- draft-only tip packets for human review,
- optional Sherlock username-correlation planning for officially published aliases,
- court-record deepening for public/official docket context,
- public docket/case-number candidate finding without PACER/private access,
- public-record source routing with explicit ready/blocked states,
- gated Sherlock execution for weak username-correlation evidence,
- Sherlock result triage and search-snippet corroboration,
- public/official camera-source routing and snippet-only search with unsafe camera discovery blocked,
- route runner for ready public routes with excerpts, hashes, deltas, and review scoring,
- review extractor for actionable/monitor/parking-lot signal decisions,
- beyond-official public OSINT routing/search/extraction for non-government source handles,
- HTML living reports for summaries, artifacts, and actionables.

## What this is not

PistaLab is **not** a stalking, doxxing, hacking, phishing, or social-engineering tool.

It must not be used to:

- contact suspects, families, employers, victims, witnesses, or associates,
- collect private/protected personal data,
- use leaked/stolen data,
- bypass authentication or scrape private areas,
- submit tips automatically,
- publish accusations.

## Quick start

From the repo root:

```bash
python3 pistalab/pistalab.py intake-text \
  --case-id sample-official-reward-notice \
  --title "Sample official reward notice" \
  --text "REWARD OF UP TO $1000000 For information leading to the arrest of Jane Doe a/k/a JD For conspiracy to commit money laundering Submit tips via Email: tips@example.gov"

python3 pistalab/pistalab.py validate pistalab/cases/sample-official-reward-notice/case.json
python3 pistalab/pistalab.py search-plan pistalab/cases/sample-official-reward-notice/case.json
```

Generated runtime artifacts are intentionally ignored by git:

```text
pistalab/cases/
pistalab/evidence/
pistalab/outputs/
pistalab/intake/
```

## Submission gate

PistaLab never submits externally by default.

External submission requires exact human approval:

```text
APPROVE SUBMISSION: <case_id> to <official channel>
```

Generic approval, checkmarks, or local workflow approvals are not enough.
