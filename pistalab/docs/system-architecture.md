# System Architecture

## Workers

1. **Notice Intake Worker**
   - Input: image/PDF/URL of official reward notice.
   - Output: structured `case.json`.

2. **Source Legitimacy Worker**
   - Confirms agency/source is official.
   - Blocks unofficial/rumor cases.

3. **Entity Extraction Worker**
   - Names, aliases, photos, locations, charges, reward amount, official channels.

4. **Search Plan Worker**
   - Builds lawful public search queries.
   - Labels risk level per query.

5. **Evidence Capture Worker**
   - Saves URLs/snippets/timestamps/screenshots/hash.
   - Does not scrape private/logged-in data.

6. **Entity Graph Worker**
   - Links aliases, companies, locations, handles, wallets, domains, news mentions.

7. **Confidence Score Worker**
   - Scores relevance and corroboration.
   - Penalizes single-source, weak alias-only matches, stale data.

8. **Tip Packet Worker**
   - Drafts concise official-style packet.
   - Includes evidence table and uncertainty.

9. **Submission Gate Worker**
   - Requires exact approval phrase before any external submission.

## Autonomy model

- Autonomous: intake, search planning, public evidence capture, scoring, packet drafting.
- Approval required: external submission, contacting anyone, buying data, using sensitive tools, running aggressive scans.
