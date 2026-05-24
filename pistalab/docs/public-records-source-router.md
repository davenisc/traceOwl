# Public Records Source Router

Command:

```bash
python3 pistalab/pistalab.py source-router pistalab/cases/<case_id>/case.json
```

Options:

```bash
--ready-only
--limit 8
--probe --probe-limit 4
```

## What it does

- Routes a case to specific public-record sources instead of generic search.
- Labels each source as `ready`, `blocked_requires_api_token`, or `blocked_private_or_paid`.
- Prioritizes official/public sources.
- Optionally probes ready public URLs.
- Does not access private, paid, sealed, or login-required sources.

## Route types

- State Department official notice/search.
- Justice.gov search / CDCA DOJ search.
- SecretService.gov search.
- CDCA court website search.
- GovInfo search.
- CourtListener public web.
- CourtListener API — blocked unless lawful API token/rate limits exist.
- RECAP storage targeted search pointer.
- Internet Archive.
- PACER — blocked private/paid path.
