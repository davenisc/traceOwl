# Tip Packet Draft Worker

Command:

```bash
./PistaLab/pistalab tip-packet PistaLab/cases/<case_id>/case.json
```

Optional:

```bash
--mode research-summary
--mode potential-tip-review
```

## What it does

- Builds a review-only packet from:
  - case file,
  - evidence ledger,
  - graph/confidence score,
  - hypotheses,
  - case memory/latest trace analysis.
- Separates verified facts from unknowns.
- Lists evidence sources.
- Lists recommended next research paths.
- Includes exact submission gate phrase.

## What it does not do

- No external submission.
- No email/signal/message to agencies.
- No contact with people.
- No doxxing/private data.

## Output

```text
outputs/<case_id>/tip-packet/tip-packet-draft.md
outputs/<case_id>/tip-packet/tip-packet-manifest.json
```

## Submission rule

External submission requires exact phrase:

```text
APPROVE SUBMISSION: <case_id> to <official channel>
```

Generic “ok”, “go”, or checkmarks do not authorize external submission.

## Example result

Current packet status:

```text
DRAFT ONLY — NOT SUBMITTED
research_confidence_score: 82
tip_readiness: NOT_READY_NEW_LEAD
external_actions_performed: false
submitted: false
```
