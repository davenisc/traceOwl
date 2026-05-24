# Route Runner Worker

Command:

```bash
python3 pistalab/pistalab.py route-runner pistalab/cases/<case_id>/case.json \
  --ensure-routers \
  --include-camera
```

## What it does

- Loads `source-router` routes marked `ready`.
- Optionally loads `camera-router` routes marked `ready*`.
- Fetches only direct public URLs or materializes `route://` pointers as public search URLs.
- Captures redacted excerpts and SHA-256 hashes.
- Appends a route ledger.
- Detects deltas against previous route hashes.
- Scores each route for review/monitoring.

## What it does not do

- No private or paid sources.
- No sealed filings.
- No PACER credentials.
- No open IP/misconfigured camera discovery.
- No face recognition or tracking.
- No contact with people/camera operators.
- No tip submission.
