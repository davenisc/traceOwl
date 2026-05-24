# Beyond Official OSINT Workers

Commands:

```bash
python3 pistalab/pistalab.py beyond-router pistalab/cases/<case_id>/case.json
python3 pistalab/pistalab.py beyond-search pistalab/cases/<case_id>/case.json
python3 pistalab/pistalab.py beyond-extract pistalab/cases/<case_id>/case.json
python3 pistalab/pistalab.py beyond-derived-search pistalab/cases/<case_id>/case.json
```

## Purpose

Government/official sites are reliable baseline but often already reviewed by law enforcement. These workers expand into lawful public non-government sources:

- crypto exchange/compliance blogs,
- blockchain intelligence public reports,
- public scam/victim-report aggregators,
- public domain/infrastructure OSINT,
- public corporate registry mentions,
- international/local media,
- sanctions/watchlist/public risk databases,
- academic/NGO scam-center reports,
- public social snippets for distinctive aliases.

## Blocked

- Leaked/private databases.
- Personal address/phone/relative searches.
- Contacting victims, witnesses, suspects, relatives, associates, companies, exchanges, or reporters.
- Paid/private investigator databases.
- Credentialed blockchain analytics unless separately authorized.
- Hacked infrastructure or dark-web access.
- Public accusation or tip submission from uncorroborated leads.
