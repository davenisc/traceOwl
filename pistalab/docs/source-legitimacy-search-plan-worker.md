# Source Legitimacy + Search Plan Worker

Commands:

```bash
./PistaLab/pistalab source-check PistaLab/cases/<case_id>/case.json --url <official-url>
./PistaLab/pistalab source-check PistaLab/cases/<case_id>/case.json --url <official-url> --evidence-file <extracted-text.txt>
./PistaLab/pistalab search-plan PistaLab/cases/<case_id>/case.json
```

## Source check

Validates:

- URL domain is in the official allowlist (`state.gov`, `secretservice.gov`, `justice.gov`, `fbi.gov`, etc.).
- Page/text contains the primary name.
- Page/text contains reward signal.
- Page/text contains official Secret Service contact signal.
- Sensitive public identifiers are redacted from local excerpts by default.

If a government page blocks direct CLI fetching but a trusted extractor/browser has the text, use `--evidence-file` or `--evidence-text` so the official URL can still be verified against extracted content.

## Search plan

Generates allowed and blocked queries:

- Allowed: official-source verification, news/court/public reporting, alias corroboration.
- Blocked: doxxing-style searches like personal phone/address/relatives.

## Example result

Official State Department URL verified:

```text
<official-source-url>
```

Generated:

```text
PistaLab/outputs/sample-official-reward-notice/source-check/source-check.json
PistaLab/outputs/sample-official-reward-notice/source-check/source-excerpt-redacted.txt
PistaLab/outputs/sample-official-reward-notice/search-plan/search-plan.json
PistaLab/outputs/sample-official-reward-notice/search-plan/search-plan.md
```

External actions performed: false.
