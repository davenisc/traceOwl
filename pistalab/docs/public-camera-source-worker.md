# Public Camera Source Worker

Commands:

```bash
python3 pistalab/pistalab.py camera-router pistalab/cases/<case_id>/case.json
python3 pistalab/pistalab.py camera-search pistalab/cases/<case_id>/case.json
```

## Scope

Allowed:

- Official DOT/traffic camera maps.
- Official municipal webcams.
- Official airport/port webcams.
- Public media livestream/webcam pages intentionally published.
- Search snippets/URLs for public reporting mentioning camera/security footage.

Blocked:

- Open IP/misconfigured cameras.
- Shodan/Censys/Insecam-style device discovery.
- Residential/workplace/private CCTV.
- Face recognition or biometric matching.
- Tracking a person across cameras.
- Contacting camera owners/operators.
- Tip submission from camera-source leads alone.
