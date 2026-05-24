# Entity Graph + Confidence Score Worker

Command:

```bash
./PistaLab/pistalab graph-score PistaLab/cases/<case_id>/case.json
```

Optional:

```bash
--ledger PistaLab/evidence/<case_id>/captures/evidence-ledger.jsonl
```

## What it does

- Reads the public evidence ledger.
- Builds entities:
  - primary person
  - aliases
  - official tip channels
  - source domains
  - search results
- Builds edges:
  - `has_alias`
  - `official_tip_channel_for_case`
  - `published_result`
  - `corroborated_by_official_source`
  - `mentioned_by_public_source`
  - `alias_seen_in_result`
- Calculates research confidence.
- Separates “public corroboration” from “new actionable tip.”

## Output files

```text
outputs/<case_id>/graph-score/entities.json
outputs/<case_id>/graph-score/entities.jsonl
outputs/<case_id>/graph-score/edges.json
outputs/<case_id>/graph-score/edges.jsonl
outputs/<case_id>/graph-score/confidence-score.json
outputs/<case_id>/graph-score/confidence-score.md
```

## Score meaning

- `STRONG_PUBLIC_CORROBORATION`: case is well-corroborated by public/official sources.
- `BASIC_CORROBORATION`: enough public confirmation to continue research.
- `WEAK_OR_INCOMPLETE`: more lawful evidence needed.

`tip_readiness` is deliberately separate. A strong score does **not** mean submit a tip. It may only mean the official notice and public reporting are confirmed.

## Example result

```text
entities: 15
edges: 20
research_confidence_score: 82
verdict: STRONG_PUBLIC_CORROBORATION
tip_readiness: NOT_READY_NEW_LEAD
external_actions_performed: false
```

Interpretation: the reward notice and public official reporting are strongly corroborated, but the current evidence does not yet identify a new lead/location/actionable tip beyond public confirmation.
