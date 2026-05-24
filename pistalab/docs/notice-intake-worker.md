# Notice Intake Worker

Command:

```bash
./PistaLab/pistalab intake-image <image> --text '<OCR text>' --case-id <case_id>
./PistaLab/pistalab intake-text --text '<notice text>' --case-id <case_id>
./PistaLab/pistalab validate PistaLab/cases/<case_id>/case.json
```

## What it does

- Creates `cases/<case_id>/case.json`.
- Copies the source image/file into `evidence/<case_id>/`.
- Records SHA-256 hash of the source file.
- Drafts `outputs/<case_id>/intake-packet.md`.
- Extracts reward amount, primary name, aliases, allegations, official channels, and agency hints when text is available.

## What it does not do

- No external submissions.
- No contact with anyone.
- No private data collection.
- No accusation/publication.

## Example intake

Created from Harvey's attached notice image plus extracted text:

```text
PistaLab/cases/sample-official-reward-notice/case.json
PistaLab/outputs/sample-official-reward-notice/intake-packet.md
PistaLab/evidence/sample-official-reward-notice/notice-source-file.json
```

Validation result: valid for research after source/channel extraction, but official source URL should still be independently verified from `state.gov` / `secretservice.gov` before any tip packet is considered.
