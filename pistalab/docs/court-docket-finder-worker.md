# Court Docket Finder Worker

Command:

```bash
python3 pistalab/pistalab.py docket-find pistalab/cases/<case_id>/case.json
```

## What it does

- Builds public docket/case-number queries from case and court-deepening clues.
- Searches only public/official sources.
- Scores docket candidates using court/caption/case-number signals.
- Extracts candidate case numbers if visible.
- Writes local trace ledger and report.

## What it does not do

- No PACER credentials.
- No paid/private docket databases.
- No sealed filings.
- No contact with court staff, victims, witnesses, defendants, relatives, employers, or associates.
- No external tip submission.

## Status values

- `DOCKET_CANDIDATE_FOUND`
- `HIGH_CONFIDENCE_DOCKET_PATH_NO_NUMBER`
- `LOW_CONFIDENCE_DOCKET_CANDIDATES`
- `NO_DOCKET_CANDIDATE_FOUND`
