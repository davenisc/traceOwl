# Review Extractor Worker

Command:

```bash
python3 pistalab/pistalab.py review-extractor pistalab/cases/<case_id>/case.json
```

Optional refresh gate:

```bash
python3 pistalab/pistalab.py review-extractor pistalab/cases/<case_id>/case.json --refresh
```

## What it does

- Reads `route-runner` captures.
- Reviews selected route tiers, default `A_REVIEW_NOW,B_KEEP_MONITORING`.
- Extracts signal buckets:
  - primary name,
  - aliases,
  - reward/wanted/tip terms,
  - court/docket terms,
  - case-status terms,
  - financial-crime terms,
  - law-enforcement terms,
  - camera context,
  - blocking/search shell content.
- Scores each route as actionable, monitor, or parking-lot low signal.
- Refreshes graph/hypotheses only when actionable signals exist and `--refresh` is passed.

## What it does not do

- No external contact.
- No tip submission.
- No private/paid sources.
- No sealed filings.
- No camera tracking or face recognition.
