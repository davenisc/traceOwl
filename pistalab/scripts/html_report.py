#!/usr/bin/env python3
"""Generate a living HTML PistaLab case report from local runtime artifacts."""
from __future__ import annotations

import argparse
import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def safe_rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def load_optional(path: Path) -> Any:
    return read_json(path) if path.exists() else None


def collect(case_id: str) -> dict[str, Any]:
    base = OUTPUTS / case_id
    paths = {
        "beyond_extract": base / "beyond-evidence-extractor" / "beyond-evidence-extractor.json",
        "beyond_search": base / "beyond-official-search" / "beyond-official-search.json",
        "beyond_derived": base / "beyond-derived-search" / "beyond-derived-search.json",
        "route_runner": base / "route-runner" / "route-runner.json",
        "review_extractor": base / "review-extractor" / "review-extractor.json",
        "docket_finder": base / "docket-finder" / "docket-finder.json",
        "camera_search": base / "camera-search" / "camera-search.json",
    }
    return {k: load_optional(v) for k, v in paths.items()} | {"paths": paths}


def artifacts(data: dict[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for row in (data.get("beyond_extract") or {}).get("extractions", []):
        for k, vals in (row.get("artifacts") or {}).items():
            out.setdefault(k, set()).update(str(v) for v in vals)
    return out


def render(case: dict[str, Any], data: dict[str, Any]) -> str:
    case_id = case["case_id"]
    ent = (case.get("entities") or [{}])[0]
    arts = artifacts(data)
    action_rows = []
    for label, key in [("Corroborate aliases", "aliases"), ("Trace shell companies", "companies"), ("Research spoofed platforms/domains", "platforms"), ("Corroborate account references", "accounts")]:
        if arts.get(key):
            action_rows.append(f"<tr><td>High</td><td>{h(label)}</td><td>{h(', '.join(sorted(arts[key])))}</td><td>Public corroboration only; no contact/private data</td></tr>")
    if not action_rows:
        action_rows.append("<tr><td>Low</td><td>Continue monitoring</td><td>No extracted artifacts yet</td><td>Baseline only</td></tr>")
    cards = []
    labels = {"aliases":"New aliases", "platforms":"Spoofed platforms", "companies":"Shell companies/entities", "accounts":"Account references", "locations":"Location anchors", "crypto_terms":"Crypto terms", "investigative_hooks":"Investigative hooks"}
    for key, label in labels.items():
        vals = sorted(arts.get(key, []))
        if vals:
            cards.append(f"<section><h3>{h(label)}</h3><ul>" + "".join(f"<li>{h(v)}</li>" for v in vals) + "</ul></section>")
    css = "body{font-family:system-ui;background:#0b1020;color:#e8eefc;margin:0;padding:28px}main{max-width:1100px;margin:auto}section,table{background:#111a2f;border:1px solid #2b3a5f;border-radius:16px;padding:16px;margin:14px 0}a{color:#7dd3fc}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #2b3a5f;padding:10px;text-align:left}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.muted{color:#94a3b8}"
    return f"<!doctype html><html><head><meta charset='utf-8'><title>PistaLab Report - {h(case_id)}</title><style>{css}</style></head><body><main><p class='muted'>Generated {now_iso()} · Living report</p><h1>PistaLab Report</h1><section><h2>{h(case.get('title') or case_id)}</h2><p>Primary entity: {h(ent.get('name'))}; aliases: {h(', '.join(ent.get('aliases') or []))}</p><p><strong>Posture:</strong> public-source research only; beyond-official artifacts are leads, not proof or submission-ready evidence.</p></section><h2>Actionables</h2><table><tr><th>Priority</th><th>Action</th><th>Detail</th><th>Guardrail</th></tr>{''.join(action_rows)}</table><h2>Artifacts</h2><div class='grid'>{''.join(cards) or '<section>No artifacts yet.</section>'}</div><section><h2>Guardrails</h2><ul><li>No leaks/private data/doxxing.</li><li>No contact.</li><li>No private cameras/face recognition/tracking.</li><li>No submission without exact human approval phrase.</li></ul></section></main></body></html>"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--output", default="")
    args = ap.parse_args()
    case_path = Path(args.case)
    case = read_json(case_path)
    data = collect(case["case_id"])
    outdir = OUTPUTS / case["case_id"] / "html-report"
    outdir.mkdir(parents=True, exist_ok=True)
    out = Path(args.output) if args.output else outdir / "index.html"
    out.write_text(render(case, data))
    manifest = {"case_id": case["case_id"], "generated_at": now_iso(), "html_report": safe_rel(out), "external_actions_performed": False}
    write_json(outdir / "html-report-manifest.json", manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
