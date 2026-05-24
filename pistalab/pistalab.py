#!/usr/bin/env python3
"""PistaLab — lawful public reward-intelligence workspace CLI.

This tool structures official reward notices into local case files.
It does not submit tips, contact anyone, hack, or use private data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
INTAKE = ROOT / "intake"
CASES = ROOT / "cases"
EVIDENCE = ROOT / "evidence"
OUTPUTS = ROOT / "outputs"

PROHIBITED_EXTERNAL_ACTIONS = [
    "submit_tip",
    "contact_suspect_or_associate",
    "publish_accusation",
    "hack_or_bypass_auth",
    "buy_or_use_leaked_private_data",
]

OFFICIAL_DOMAINS = [
    "state.gov",
    "secretservice.gov",
    "justice.gov",
    "fbi.gov",
    "ice.gov",
    "dea.gov",
    "treasury.gov",
    "ofac.treasury.gov",
]

SENSITIVE_LABELS = ["national id", "passport", "u.s. visas", "dob"]


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "case"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def extract_notice_fields(text: str) -> dict[str, Any]:
    clean = re.sub(r"\s+", " ", text).strip()
    amount = None
    m = re.search(r"\$\s*([0-9][0-9,]*(?:\.\d+)?)\s*(million|m|usd)?", clean, re.I)
    if m:
        raw = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").lower()
        amount = int(raw * 1_000_000) if suffix in {"million", "m"} else int(raw)
    name = ""
    m = re.search(r"arrest of\s+(.+?)(?:\s+a/k/a|\s+aka|\s+For\s+|$)", clean, re.I)
    if m:
        name = re.sub(r"\s+", " ", m.group(1)).strip(" .,")
    aliases: list[str] = []
    aka_match = re.search(r"a/k/a\s+(.+?)(?:For conspiracy|Submit tips|$)", clean, re.I)
    if aka_match:
        aliases = [a.strip(' "“”.,') for a in re.split(r",|;| and ", aka_match.group(1)) if a.strip(' "“”.,')]
    allegations: list[str] = []
    for pat in [r"For (conspiracy to commit [^.]+?)(?: Submit|$)", r"For ([^.]+?)(?: Submit|$)"]:
        mm = re.search(pat, clean, re.I)
        if mm:
            allegations.append(mm.group(1).strip(" ."))
            break
    channels = []
    sig = re.search(r"Signal[:\s]+([A-Za-z0-9_.-]+)", clean, re.I)
    if sig:
        channels.append({"type": "Signal", "value": sig.group(1), "agency": "Unknown/verify"})
    email = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", clean, re.I)
    if email:
        channels.append({"type": "Email", "value": email.group(0), "agency": "Unknown/verify"})
    agency = ""
    if re.search(r"Secret Service|USSS", clean, re.I):
        agency = "U.S. Secret Service"
    if re.search(r"Department of State|state\.gov", clean, re.I):
        agency = "U.S. Department of State / U.S. Secret Service" if agency else "U.S. Department of State"
    return {
        "name": name,
        "aliases": aliases,
        "reward_amount_usd": amount,
        "allegations": allegations,
        "official_channels": channels,
        "agency": agency or "Unknown/needs verification",
    }


def build_case(case_id: str, title: str, source: dict[str, Any], fields: dict[str, Any], text: str = "") -> dict[str, Any]:
    person = {
        "type": "person",
        "name": fields.get("name") or title,
        "aliases": fields.get("aliases") or [],
        "allegation": "; ".join(fields.get("allegations") or []),
    }
    return {
        "case_id": case_id,
        "title": title,
        "status": "INTAKE",
        "reward_amount_usd": fields.get("reward_amount_usd"),
        "source": source,
        "entities": [person],
        "allegations": fields.get("allegations") or [],
        "official_channels": fields.get("official_channels") or [],
        "constraints": [
            "Public-source evidence only",
            "No external submission without exact approval phrase",
            "No contacting suspects, associates, employers, family, victims, or witnesses",
            "No hacking, credential abuse, leaked private data, or auth bypass",
            "No public accusation or publication of findings",
        ],
        "raw_text": text,
        "created_at": now_iso(),
        "external_actions_performed": False,
        "blocked_external_actions": PROHIBITED_EXTERNAL_ACTIONS,
    }


def write_case_bundle(case: dict[str, Any], source_file: Path | None = None) -> dict[str, str]:
    case_id = case["case_id"]
    cdir = CASES / case_id
    cdir.mkdir(parents=True, exist_ok=True)
    case_path = cdir / "case.json"
    write_json(case_path, case)
    if source_file and source_file.exists():
        ed = EVIDENCE / case_id
        ed.mkdir(parents=True, exist_ok=True)
        dest = ed / source_file.name
        if source_file.resolve() != dest.resolve():
            shutil.copy2(source_file, dest)
        evidence = {
            "case_id": case_id,
            "kind": "notice_source_file",
            "path": str(dest.relative_to(ROOT)),
            "sha256": sha256_file(dest),
            "captured_at": now_iso(),
            "external_actions_performed": False,
        }
        write_json(ed / "notice-source-file.json", evidence)
    packet = draft_intake_packet(case)
    outdir = OUTPUTS / case_id
    outdir.mkdir(parents=True, exist_ok=True)
    packet_path = outdir / "intake-packet.md"
    packet_path.write_text(packet)
    return {"case": str(case_path), "packet": str(packet_path)}


def draft_intake_packet(case: dict[str, Any]) -> str:
    entity = (case.get("entities") or [{}])[0]
    lines = [
        f"# Intake Packet — {case.get('title')}",
        "",
        f"- Case ID: `{case.get('case_id')}`",
        f"- Status: {case.get('status')}",
        f"- Reward: ${case.get('reward_amount_usd'):,}" if case.get("reward_amount_usd") else "- Reward: unknown",
        f"- Agency/source: {case.get('source', {}).get('agency', 'unknown')}",
        f"- External actions performed: {case.get('external_actions_performed')}",
        "",
        "## Primary entity",
        "",
        f"- Name: {entity.get('name')}",
        f"- Aliases: {', '.join(entity.get('aliases') or []) or 'none extracted'}",
        f"- Allegation: {entity.get('allegation') or 'none extracted'}",
        "",
        "## Official channels extracted",
        "",
    ]
    for ch in case.get("official_channels") or []:
        lines.append(f"- {ch.get('type')}: `{ch.get('value')}` ({ch.get('agency')})")
    if not case.get("official_channels"):
        lines.append("- none extracted; verify source manually")
    lines += [
        "",
        "## Immediate next safe actions",
        "",
        "1. Verify official source URL/page from agency website.",
        "2. Build public-source search plan for names and aliases.",
        "3. Capture evidence with URLs, timestamps, snippets, and hashes.",
        "4. Score any lead with corroboration and alternative explanations.",
        "5. Draft tip packet only; do not submit externally without exact approval phrase.",
        "",
        "## Submission gate",
        "",
        "External submission requires exact phrase:",
        "",
        f"`APPROVE SUBMISSION: {case.get('case_id')} to <official channel>`",
        "",
    ]
    return "\n".join(lines)



def strip_html(value: str) -> str:
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.S | re.I)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.S | re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8217;", "'").replace("&#8220;", '"').replace("&#8221;", '"')
    return re.sub(r"\s+", " ", value).strip()


def fetch_public_url(url: str, timeout: int = 15) -> tuple[int, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "PistaLab/0.1 lawful-public-source-check"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(1_500_000).decode("utf-8", "ignore")
        return resp.status, resp.headers.get("content-type", ""), raw


def source_domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def is_official_domain(url: str) -> bool:
    host = source_domain(url)
    return any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS)


def redact_sensitive_lines(text: str) -> str:
    parts = re.split(r"(?=(?:NAME|ALIASES|DOB|POB|NATIONALITY|PASSPORTS|U\.S\. VISAS|NATIONAL ID|HEIGHT|WEIGHT|HAIR COLOR|EYE COLOR):)", text, flags=re.I)
    kept = []
    for part in parts:
        lower = part.lower().strip()
        if any(lower.startswith(label) for label in SENSITIVE_LABELS):
            label = part.split(":", 1)[0].strip() if ":" in part else "sensitive_field"
            kept.append(f"{label}: [REDACTED_IN_PISTALAB]")
        elif part.strip():
            kept.append(part.strip())
    return "\n".join(kept)


def extract_source_summary(text: str, case: dict[str, Any]) -> dict[str, Any]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    aliases = entity.get("aliases", []) or []
    hits = {
        "name_present": bool(name and re.search(re.escape(name), text, re.I)),
        "aliases_present": [a for a in aliases if a and re.search(re.escape(a), text, re.I)],
        "reward_present": bool(re.search(r"\$?\s*4\s*million|4\s*MILLION|4,000,000", text, re.I)),
        "secret_service_channel_present": bool(re.search(r"MostWanted@usss\.dhs\.gov|USSSMostWanted\.1865|Secret Service", text, re.I)),
    }
    return hits


def save_case(case: dict[str, Any]) -> Path:
    cdir = CASES / case["case_id"]
    cdir.mkdir(parents=True, exist_ok=True)
    path = cdir / "case.json"
    write_json(path, case)
    return path


def cmd_source_check(args: argparse.Namespace) -> None:
    case_path = Path(args.case)
    case = read_json(case_path)
    url = args.url or case.get("source", {}).get("official_url") or case.get("source", {}).get("url", "")
    if not url or url in {"local-image", "manual-text"} or url.startswith("image-"):
        raise SystemExit("Source check needs an official --url, e.g. a state.gov or secretservice.gov page.")
    report_dir = OUTPUTS / case["case_id"] / "source-check"
    report_dir.mkdir(parents=True, exist_ok=True)
    status, content_type, raw = fetch_public_url(url)
    text = strip_html(raw)
    if args.evidence_file:
        text = Path(args.evidence_file).read_text()
        content_type = content_type + "; evidence_file_override"
    if args.evidence_text:
        text = args.evidence_text
        content_type = content_type + "; evidence_text_override"
    official = is_official_domain(url)
    hits = extract_source_summary(text, case)
    verified = official and hits["name_present"] and hits["reward_present"] and hits["secret_service_channel_present"]
    summary = {
        "case_id": case["case_id"],
        "checked_at": now_iso(),
        "url": url,
        "domain": source_domain(url),
        "http_status": status,
        "content_type": content_type,
        "official_domain": official,
        "verification_hits": hits,
        "source_legitimacy": "verified_official" if verified else "needs_review",
        "external_actions_performed": False,
        "sensitive_public_fields_redacted_in_outputs": True,
    }
    write_json(report_dir / "source-check.json", summary)
    redacted = redact_sensitive_lines(text[:8000])
    (report_dir / "source-excerpt-redacted.txt").write_text(redacted + "\n")
    case.setdefault("source", {})["official_url"] = url
    case["source"]["legitimacy"] = summary["source_legitimacy"]
    case["source"]["last_checked_at"] = summary["checked_at"]
    case["source"]["official_domain"] = official
    case["status"] = "VALIDATING" if summary["source_legitimacy"] != "verified_official" else "RESEARCHING"
    save_case(case)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def safe_search_queries(case: dict[str, Any]) -> list[dict[str, Any]]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    aliases = entity.get("aliases") or []
    allegations = " ".join(case.get("allegations") or [])
    queries: list[dict[str, Any]] = []
    def add(q: str, purpose: str, risk: str = "low", allowed: bool = True):
        queries.append({"query": q, "purpose": purpose, "risk": risk, "allowed": allowed})
    if name:
        add(f'"{name}" "reward" "Secret Service"', "Verify official/public reward references")
        add(f'"{name}" "money laundering"', "Find public news/court references")
        add(f'"{name}" site:justice.gov OR site:state.gov', "Find official U.S. government references")
    for alias in aliases:
        add(f'"{alias}" "{name}"', "Alias corroboration against primary identity")
        add(f'"{alias}" "money laundering"', "Alias-related public reporting", risk="medium")
    if allegations:
        add(f'"{name}" "conspiracy to commit money laundering"', "Allegation-specific public corroboration")
    for channel in case.get("official_channels") or []:
        value = channel.get("value", "")
        if value:
            add(f'"{name}" "{value}"', "Confirm official tip channel references")
    # Explicit blocked query patterns to prevent drift.
    for alias in aliases[:3]:
        add(f'"{alias}" personal phone address relatives', "Blocked: private/doxxing-style search", risk="prohibited", allowed=False)
    return queries


def cmd_search_plan(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    queries = safe_search_queries(case)
    outdir = OUTPUTS / case["case_id"] / "search-plan"
    outdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "case_id": case["case_id"],
        "generated_at": now_iso(),
        "queries": queries,
        "allowed_count": sum(1 for q in queries if q["allowed"]),
        "blocked_count": sum(1 for q in queries if not q["allowed"]),
        "external_actions_performed": False,
        "policy": "Public-source searches only. No contact, no doxxing, no hacked/leaked data.",
    }
    write_json(outdir / "search-plan.json", payload)
    lines = [f"# Search Plan — {case['case_id']}", "", "- External actions performed: false", ""]
    for q in queries:
        mark = "ALLOW" if q["allowed"] else "BLOCK"
        lines += [f"## {mark}: `{q['query']}`", f"- Purpose: {q['purpose']}", f"- Risk: {q['risk']}", ""]
    (outdir / "search-plan.md").write_text("\n".join(lines))
    print(json.dumps({"case_id": case["case_id"], "allowed": payload["allowed_count"], "blocked": payload["blocked_count"], "outdir": str(outdir), "external_actions_performed": False}, indent=2, ensure_ascii=False))


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "ignore")).hexdigest()


def ddg_search(query: str, limit: int = 5) -> list[dict[str, str]]:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        status, content_type, html = fetch_public_url(url, timeout=20)
    except Exception as exc:
        return [{"title": "SEARCH_ERROR", "url": url, "snippet": str(exc)}]
    results: list[dict[str, str]] = []
    for block in html.split('<div class="result'):
        m = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        href = m.group(1)
        title = strip_html(m.group(2))
        if "uddg=" in href:
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            href = params.get("uddg", [href])[0]
        sm = re.search(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>', block, re.S)
        snippet = strip_html((sm.group(1) or sm.group(2)) if sm else "")
        results.append({"title": title, "url": href, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


def evidence_relevance_score(case: dict[str, Any], result: dict[str, str]) -> dict[str, Any]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    aliases = entity.get("aliases") or []
    haystack = f"{result.get('title','')} {result.get('snippet','')} {result.get('url','')}"
    score = 0
    reasons: list[str] = []
    if name and re.search(re.escape(name), haystack, re.I):
        score += 35; reasons.append("primary name match")
    alias_hits = []
    for a in aliases:
        if not a:
            continue
        pattern = (r"\b" + re.escape(a) + r"\b") if len(a) <= 3 else re.escape(a)
        if re.search(pattern, haystack, re.I):
            alias_hits.append(a)
    if alias_hits:
        score += min(20, 8 * len(alias_hits)); reasons.append("alias match: " + ", ".join(alias_hits))
    if re.search(r"money laundering|conspiracy|fugitive|reward|Secret Service|State Department|USSS", haystack, re.I):
        score += 20; reasons.append("case-topic terms")
    if is_official_domain(result.get("url", "")):
        score += 20; reasons.append("official domain")
    elif source_domain(result.get("url", "")):
        score += 5; reasons.append("public web source")
    return {"score": min(score, 100), "reasons": reasons, "alias_hits": alias_hits}


def safe_fetch_excerpt(url: str, max_chars: int = 2500) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        return {"fetched": False, "reason": "unsupported_url_scheme"}
    try:
        status, content_type, raw = fetch_public_url(url, timeout=15)
        text = redact_sensitive_lines(strip_html(raw))[:max_chars]
        return {
            "fetched": True,
            "http_status": status,
            "content_type": content_type,
            "excerpt": text,
            "excerpt_sha256": sha256_text(text),
        }
    except Exception as exc:
        return {"fetched": False, "reason": str(exc)[:300]}


def cmd_capture_evidence(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    plan_path = Path(args.plan) if args.plan else OUTPUTS / case_id / "search-plan" / "search-plan.json"
    if not plan_path.exists():
        raise SystemExit(f"Search plan not found: {plan_path}. Run search-plan first.")
    plan = read_json(plan_path)
    outdir = EVIDENCE / case_id / "captures"
    outdir.mkdir(parents=True, exist_ok=True)
    ledger_path = outdir / "evidence-ledger.jsonl"
    report_rows: list[dict[str, Any]] = []
    allowed_queries = [q for q in plan.get("queries", []) if q.get("allowed")]
    if args.max_queries:
        allowed_queries = allowed_queries[: args.max_queries]
    for q in allowed_queries:
        query = q["query"]
        results = ddg_search(query, limit=args.per_query)
        for idx, result in enumerate(results, 1):
            captured_at = now_iso()
            if result.get("title") == "SEARCH_ERROR":
                row = {
                    "case_id": case_id,
                    "kind": "search_error",
                    "query": query,
                    "error": result.get("snippet"),
                    "captured_at": captured_at,
                    "external_actions_performed": False,
                }
                append_jsonl(ledger_path, row)
                report_rows.append(row)
                continue
            rel = evidence_relevance_score(case, result)
            page = safe_fetch_excerpt(result.get("url", ""), max_chars=args.excerpt_chars) if args.fetch_pages else {"fetched": False, "reason": "fetch_pages_disabled"}
            row = {
                "case_id": case_id,
                "kind": "public_search_result",
                "query": query,
                "query_purpose": q.get("purpose"),
                "query_risk": q.get("risk"),
                "rank": idx,
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "domain": source_domain(result.get("url", "")),
                "snippet": redact_sensitive_lines(result.get("snippet", "")),
                "captured_at": captured_at,
                "url_sha256": sha256_text(result.get("url", "")),
                "snippet_sha256": sha256_text(result.get("snippet", "")),
                "official_domain": is_official_domain(result.get("url", "")),
                "relevance_score": rel["score"],
                "relevance_reasons": rel["reasons"],
                "alias_hits": rel["alias_hits"],
                "page_fetch": page,
                "external_actions_performed": False,
                "policy": "public search only; no contact/submission/private data",
            }
            append_jsonl(ledger_path, row)
            report_rows.append(row)
        time.sleep(args.delay)
    report_rows.sort(key=lambda r: r.get("relevance_score", 0), reverse=True)
    summary = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "ledger": str(ledger_path),
        "queries_run": len(allowed_queries),
        "results_captured": sum(1 for r in report_rows if r.get("kind") == "public_search_result"),
        "errors": sum(1 for r in report_rows if r.get("kind") == "search_error"),
        "external_actions_performed": False,
        "fetch_pages": args.fetch_pages,
        "top_results": report_rows[: args.report_limit],
    }
    write_json(outdir / "capture-summary.json", summary)
    lines = [
        f"# Evidence Capture Summary — {case_id}",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Queries run: {summary['queries_run']}",
        f"- Results captured: {summary['results_captured']}",
        f"- Errors: {summary['errors']}",
        f"- External actions performed: {summary['external_actions_performed']}",
        f"- Ledger: `{ledger_path}`",
        "",
        "## Top results",
        "",
    ]
    for row in summary["top_results"]:
        if row.get("kind") != "public_search_result":
            continue
        lines += [
            f"### {row.get('title') or row.get('url')}",
            f"- URL: {row.get('url')}",
            f"- Domain: {row.get('domain')}",
            f"- Query: `{row.get('query')}`",
            f"- Relevance: {row.get('relevance_score')} ({', '.join(row.get('relevance_reasons') or [])})",
            f"- Snippet: {row.get('snippet')}",
            "",
        ]
    (outdir / "capture-summary.md").write_text("\n".join(lines))
    case["status"] = "RESEARCHING"
    case.setdefault("evidence", {})["latest_capture_summary"] = str((outdir / "capture-summary.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({
        "case_id": case_id,
        "queries_run": summary["queries_run"],
        "results_captured": summary["results_captured"],
        "ledger": str(ledger_path),
        "summary": str(outdir / "capture-summary.md"),
        "external_actions_performed": False,
    }, indent=2, ensure_ascii=False))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def entity_id(kind: str, value: str) -> str:
    return f"{kind}:{slugify(value)[:80]}"


def add_entity(entities: dict[str, dict[str, Any]], kind: str, value: str, **attrs: Any) -> str:
    eid = entity_id(kind, value)
    item = entities.setdefault(eid, {"id": eid, "kind": kind, "value": value, "mentions": 0, "sources": []})
    item["mentions"] += 1
    for k, v in attrs.items():
        if v not in (None, "", []):
            item[k] = v
    return eid


def add_edge(edges: list[dict[str, Any]], src: str, dst: str, relation: str, source_url: str = "", confidence: int = 50, evidence: str = "") -> None:
    edges.append({
        "id": sha256_text(f"{src}|{relation}|{dst}|{source_url}")[:16],
        "source": src,
        "target": dst,
        "relation": relation,
        "source_url": source_url,
        "confidence": confidence,
        "evidence": evidence[:500],
    })


def build_entity_graph(case: dict[str, Any], ledger_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    entities: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    primary = (case.get("entities") or [{}])[0]
    primary_name = primary.get("name", "")
    primary_id = add_entity(entities, "person", primary_name, role="primary_subject")
    for alias in primary.get("aliases") or []:
        aid = add_entity(entities, "alias", alias)
        add_edge(edges, primary_id, aid, "has_alias", confidence=90, evidence="official notice alias")
    for ch in case.get("official_channels") or []:
        cid = add_entity(entities, "official_channel", ch.get("value", ""), channel_type=ch.get("type"))
        add_edge(edges, primary_id, cid, "official_tip_channel_for_case", confidence=90, evidence="official notice channel")
    source_counts = {"official": 0, "public": 0, "other": 0}
    domains: set[str] = set()
    alias_corroboration: dict[str, int] = {alias: 0 for alias in primary.get("aliases") or []}
    topic_hits = 0
    for row in ledger_rows:
        if row.get("kind") != "public_search_result":
            continue
        url = row.get("url", "")
        domain = row.get("domain") or source_domain(url)
        if domain:
            domains.add(domain)
        sid = add_entity(entities, "source", domain or url, official=row.get("official_domain", False))
        rid = add_entity(entities, "result", row.get("title") or url, url=url, relevance_score=row.get("relevance_score", 0))
        add_edge(edges, sid, rid, "published_result", source_url=url, confidence=60, evidence=row.get("snippet", ""))
        if row.get("official_domain"):
            source_counts["official"] += 1
            add_edge(edges, primary_id, sid, "corroborated_by_official_source", source_url=url, confidence=80, evidence=row.get("title", ""))
        else:
            source_counts["public"] += 1
            add_edge(edges, primary_id, sid, "mentioned_by_public_source", source_url=url, confidence=50, evidence=row.get("title", ""))
        for alias in row.get("alias_hits") or []:
            alias_corroboration[alias] = alias_corroboration.get(alias, 0) + 1
            aid = add_entity(entities, "alias", alias)
            add_edge(edges, aid, rid, "alias_seen_in_result", source_url=url, confidence=55, evidence=row.get("title", ""))
        if re.search(r"money laundering|conspiracy|fugitive|reward|sentenced|Secret Service|State Department|Justice", f"{row.get('title','')} {row.get('snippet','')}", re.I):
            topic_hits += 1
    metrics = {
        "entity_count": len(entities),
        "edge_count": len(edges),
        "domains": sorted(domains),
        "source_counts": source_counts,
        "alias_corroboration": alias_corroboration,
        "topic_hits": topic_hits,
    }
    return list(entities.values()), edges, metrics


def confidence_assessment(case: dict[str, Any], metrics: dict[str, Any], ledger_rows: list[dict[str, Any]]) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    cautions: list[str] = []
    source_legitimacy = case.get("source", {}).get("legitimacy")
    if source_legitimacy == "verified_official":
        score += 30; reasons.append("official notice verified")
    else:
        cautions.append("official notice not verified")
    official_count = metrics.get("source_counts", {}).get("official", 0)
    public_count = metrics.get("source_counts", {}).get("public", 0)
    if official_count >= 2:
        score += 20; reasons.append("multiple official-source results")
    elif official_count == 1:
        score += 12; reasons.append("one official-source result")
    if public_count >= 2:
        score += 12; reasons.append("multiple public corroborating results")
    elif public_count == 1:
        score += 6; reasons.append("one public corroborating result")
    if metrics.get("topic_hits", 0) >= 3:
        score += 12; reasons.append("case-topic terms recur across evidence")
    alias_hits = sum(metrics.get("alias_corroboration", {}).values())
    if alias_hits:
        score += min(12, alias_hits * 3); reasons.append(f"alias corroboration hits: {alias_hits}")
    domains = metrics.get("domains", [])
    if len(domains) >= 3:
        score += 8; reasons.append("3+ distinct domains")
    top_relevance = max([int(r.get("relevance_score") or 0) for r in ledger_rows if r.get("kind") == "public_search_result"] or [0])
    if top_relevance >= 55:
        score += 6; reasons.append("high-relevance result present")
    if not any(r.get("kind") == "public_search_result" and not r.get("official_domain") for r in ledger_rows):
        cautions.append("evidence is mostly official confirmation; no independent public lead yet")
    # This worker scores research confidence, not tip worthiness.
    research_confidence = min(score, 100)
    if research_confidence >= 75:
        verdict = "STRONG_PUBLIC_CORROBORATION"
    elif research_confidence >= 50:
        verdict = "BASIC_CORROBORATION"
    else:
        verdict = "WEAK_OR_INCOMPLETE"
    tip_readiness = "NOT_READY_NEW_LEAD" if verdict in {"STRONG_PUBLIC_CORROBORATION", "BASIC_CORROBORATION"} else "NOT_READY"
    if public_count >= 2 and alias_hits >= 2:
        tip_readiness = "RESEARCH_PACKET_READY_NOT_TIP"
    return {
        "case_id": case.get("case_id"),
        "generated_at": now_iso(),
        "research_confidence_score": research_confidence,
        "verdict": verdict,
        "tip_readiness": tip_readiness,
        "reasons": reasons,
        "cautions": cautions,
        "metrics": metrics,
        "external_actions_performed": False,
        "policy": "This is evidence-corroboration scoring only, not authorization to submit tips or accuse anyone.",
    }


def cmd_graph_score(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    ledger_path = Path(args.ledger) if args.ledger else EVIDENCE / case_id / "captures" / "evidence-ledger.jsonl"
    rows = read_jsonl(ledger_path)
    if not rows:
        raise SystemExit(f"No evidence rows found: {ledger_path}. Run capture-evidence first.")
    entities, edges, metrics = build_entity_graph(case, rows)
    assessment = confidence_assessment(case, metrics, rows)
    outdir = OUTPUTS / case_id / "graph-score"
    outdir.mkdir(parents=True, exist_ok=True)
    write_json(outdir / "entities.json", entities)
    write_json(outdir / "edges.json", edges)
    with (outdir / "entities.jsonl").open("w", encoding="utf-8") as f:
        for item in entities:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    with (outdir / "edges.jsonl").open("w", encoding="utf-8") as f:
        for item in edges:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    write_json(outdir / "confidence-score.json", assessment)
    lines = [
        f"# Entity Graph + Confidence Score — {case_id}",
        "",
        f"- Generated: {assessment['generated_at']}",
        f"- Research confidence: {assessment['research_confidence_score']}",
        f"- Verdict: {assessment['verdict']}",
        f"- Tip readiness: {assessment['tip_readiness']}",
        f"- External actions performed: {assessment['external_actions_performed']}",
        "",
        "## Reasons",
        "",
    ]
    lines += [f"- {r}" for r in assessment["reasons"]] or ["- none"]
    lines += ["", "## Cautions", ""]
    lines += [f"- {c}" for c in assessment["cautions"]] or ["- none"]
    lines += ["", "## Metrics", "", "```json", json.dumps(metrics, indent=2, ensure_ascii=False), "```", ""]
    (outdir / "confidence-score.md").write_text("\n".join(lines))
    case.setdefault("graph_score", {})["latest"] = str((outdir / "confidence-score.json").relative_to(ROOT))
    case["status"] = "RESEARCHING"
    save_case(case)
    print(json.dumps({
        "case_id": case_id,
        "entities": len(entities),
        "edges": len(edges),
        "research_confidence_score": assessment["research_confidence_score"],
        "verdict": assessment["verdict"],
        "tip_readiness": assessment["tip_readiness"],
        "outdir": str(outdir),
        "external_actions_performed": False,
    }, indent=2, ensure_ascii=False))


def hypothesis_templates(case: dict[str, Any], assessment: dict[str, Any], ledger_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    aliases = entity.get("aliases") or []
    official_url = case.get("source", {}).get("official_url", "")
    domains = assessment.get("metrics", {}).get("domains", [])
    base: list[dict[str, Any]] = []

    def hyp(kind: str, title: str, rationale: str, allowed_queries: list[str], evidence_basis: list[str], priority: int, blocked_paths: list[str] | None = None) -> None:
        base.append({
            "hypothesis_id": f"hyp-{slugify(kind + '-' + title)[:70]}",
            "kind": kind,
            "title": title,
            "rationale": rationale,
            "priority_score": priority,
            "status": "OPEN_PUBLIC_RESEARCH",
            "allowed_queries": [{"query": q, "allowed": True, "risk": "low" if "site:" in q or name in q else "medium"} for q in allowed_queries],
            "evidence_basis": evidence_basis,
            "blocked_paths": blocked_paths or [
                "Do not search personal phone/address/relatives",
                "Do not contact people/entities",
                "Do not use leaked/private data",
                "Do not submit externally without exact approval phrase",
            ],
            "external_actions_performed": False,
        })

    official_sources = [r for r in ledger_rows if r.get("kind") == "public_search_result" and r.get("official_domain")]
    public_sources = [r for r in ledger_rows if r.get("kind") == "public_search_result" and not r.get("official_domain")]
    official_basis = [r.get("url", "") for r in official_sources[:4]] or ([official_url] if official_url else [])
    public_basis = [r.get("url", "") for r in public_sources[:3]]

    hyp(
        "court-records",
        "Court docket can expose lawful shell-company and co-conspirator context",
        "Justice.gov sources mention conviction/sentencing and laundering through U.S. shell-company bank accounts. Public court records may identify case numbers, charging documents, forfeiture facts, companies, or co-conspirators without private-data collection.",
        [
            f'"{name}" "Central District of California" "case"',
            f'"{name}" "plea agreement"',
            f'"{name}" "sentenced" "73 million"',
            f'"{name}" site:justice.gov "Central District of California"',
        ],
        official_basis,
        88,
        blocked_paths=["Do not pull sealed filings", "Do not buy private database records", "Do not contact victims/witnesses/co-defendants"],
    )

    hyp(
        "official-expansion",
        "Official sources may list additional identifiers or reward program updates",
        "The verified State Department page and reward PDF are canonical. Related State/USSS/DOJ pages may update status, channels, case narrative, or official identifiers. This is safest and should run first.",
        [
            f'"{name}" site:state.gov',
            f'"{name}" site:secretservice.gov',
            f'"{name}" site:justice.gov',
            f'"{name}" "Transnational Organized Crime Rewards Program"',
        ],
        official_basis,
        92,
    )

    if aliases:
        hyp(
            "alias-corroboration",
            "Aliases may connect to public articles, court docs, or official notices",
            "Aliases are published by the official reward notice. Searching them only in combination with primary case terms can corroborate identity while avoiding broad doxxing-style searches.",
            [q for alias in aliases for q in [
                f'"{alias}" "{name}"',
                f'"{alias}" "money laundering" "{name}"',
                f'"{alias}" "Secret Service"',
            ]],
            official_basis,
            74,
            blocked_paths=["Do not run alias + address/phone/relatives queries", "Do not contact matching social accounts", "Treat alias-only matches as weak until independently corroborated"],
        )

    hyp(
        "crypto-scam-laundering-context",
        "Public crypto scam reporting may reveal lawful entity/network context",
        "The official narrative ties the case to Southeast Asia cyber scam proceeds and cryptocurrency laundering. Public reporting may identify organizations, scam typologies, dates, or jurisdictions useful for a research packet.",
        [
            f'"{name}" "cryptocurrency scam"',
            f'"{name}" "Southeast Asia" "scam"',
            f'"{name}" "wire transfers" "shell companies"',
            f'"{name}" "victim funds"',
        ],
        official_basis + public_basis,
        70,
        blocked_paths=["Do not trace private wallets unless published by official/public sources", "Do not interact with blockchain addresses", "Do not contact alleged victims"],
    )

    if "binance.com" in domains:
        hyp(
            "public-media-crosscheck",
            "Non-official public articles should be cross-checked, not trusted",
            "The current ledger has at least one non-official public source. It can broaden context, but should be treated as secondary until corroborated by official documents.",
            [
                f'"{name}" "Binance" "73"',
                f'"{name}" "20 years" "cryptocurrency investment scam"',
                f'"{name}" "global cryptocurrency investment scam"',
            ],
            public_basis + official_basis,
            58,
            blocked_paths=["Do not rely on crypto/social posts as primary evidence", "Do not submit tips based only on media summaries"],
        )

    return sorted(base, key=lambda h: h["priority_score"], reverse=True)


def cmd_hypotheses(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    ledger_path = Path(args.ledger) if args.ledger else EVIDENCE / case_id / "captures" / "evidence-ledger.jsonl"
    score_path = Path(args.score) if args.score else OUTPUTS / case_id / "graph-score" / "confidence-score.json"
    rows = read_jsonl(ledger_path)
    if not rows:
        raise SystemExit(f"No evidence ledger found: {ledger_path}. Run capture-evidence first.")
    if not score_path.exists():
        raise SystemExit(f"No confidence score found: {score_path}. Run graph-score first.")
    assessment = read_json(score_path)
    hypotheses = hypothesis_templates(case, assessment, rows)
    if args.limit:
        hypotheses = hypotheses[: args.limit]
    outdir = OUTPUTS / case_id / "hypotheses"
    outdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "hypothesis_count": len(hypotheses),
        "hypotheses": hypotheses,
        "external_actions_performed": False,
        "policy": "Hypotheses are public-research routes only, not accusations and not tip submissions.",
    }
    write_json(outdir / "lead-hypotheses.json", payload)
    lines = [
        f"# Lead Hypotheses — {case_id}",
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Hypotheses: {len(hypotheses)}",
        "- External actions performed: false",
        "- Policy: public research only; no contact, no doxxing, no submission.",
        "",
    ]
    for h in hypotheses:
        lines += [
            f"## {h['priority_score']} — {h['title']}",
            "",
            f"- ID: `{h['hypothesis_id']}`",
            f"- Kind: {h['kind']}",
            f"- Status: {h['status']}",
            f"- Rationale: {h['rationale']}",
            "",
            "### Allowed queries",
            "",
        ]
        lines += [f"- `{q['query']}` — risk: {q['risk']}" for q in h["allowed_queries"]]
        lines += ["", "### Evidence basis", ""]
        lines += [f"- {u}" for u in h["evidence_basis"]] or ["- none"]
        lines += ["", "### Blocked paths", ""]
        lines += [f"- {b}" for b in h["blocked_paths"]]
        lines += [""]
    (outdir / "lead-hypotheses.md").write_text("\n".join(lines))
    case.setdefault("hypotheses", {})["latest"] = str((outdir / "lead-hypotheses.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({
        "case_id": case_id,
        "hypotheses": len(hypotheses),
        "top_hypothesis": hypotheses[0]["title"] if hypotheses else "",
        "outdir": str(outdir),
        "external_actions_performed": False,
    }, indent=2, ensure_ascii=False))


def update_case_memory(case: dict[str, Any], entry: dict[str, Any]) -> Path:
    cdir = CASES / case["case_id"]
    cdir.mkdir(parents=True, exist_ok=True)
    memory_path = cdir / "case-memory.json"
    memory = read_json(memory_path) if memory_path.exists() else {
        "case_id": case["case_id"],
        "created_at": now_iso(),
        "runs": [],
        "learned": [],
        "external_actions_performed": False,
    }
    memory["updated_at"] = now_iso()
    memory.setdefault("runs", []).append(entry)
    # Keep durable lessons compact.
    if entry.get("lead_analysis", {}).get("new_lead_status"):
        memory.setdefault("learned", []).append({
            "at": entry.get("ran_at"),
            "status": entry["lead_analysis"].get("new_lead_status"),
            "summary": entry["lead_analysis"].get("summary"),
        })
    write_json(memory_path, memory)
    return memory_path


def analyze_trace_for_leads(case: dict[str, Any], traced_rows: list[dict[str, Any]], hypotheses: list[dict[str, Any]]) -> dict[str, Any]:
    public_results = [r for r in traced_rows if r.get("kind") in {"hypothesis_search_result", "hypothesis_basis_result"}]
    official = [r for r in public_results if r.get("official_domain")]
    non_official = [r for r in public_results if not r.get("official_domain")]
    high = [r for r in public_results if int(r.get("relevance_score") or 0) >= 55]
    alias_hits = sorted({a for r in public_results for a in (r.get("alias_hits") or [])})
    domains = sorted({r.get("domain") for r in public_results if r.get("domain")})
    by_hyp: dict[str, dict[str, Any]] = {}
    for r in public_results:
        hid = r.get("hypothesis_id") or "unknown"
        bucket = by_hyp.setdefault(hid, {"results": 0, "high_relevance": 0, "official": 0, "domains": set()})
        bucket["results"] += 1
        if int(r.get("relevance_score") or 0) >= 55:
            bucket["high_relevance"] += 1
        if r.get("official_domain"):
            bucket["official"] += 1
        if r.get("domain"):
            bucket["domains"].add(r.get("domain"))
    by_hyp_json = {k: {**v, "domains": sorted(v["domains"])} for k, v in by_hyp.items()}
    # Conservative signal: a new lead needs non-official corroboration or court/source expansion beyond just the canonical notice.
    new_lead_status = "NO_NEW_ACTIONABLE_LEAD"
    summary = "Trace added corroborating public/official evidence, but no new actionable tip was identified."
    if len(non_official) >= 2 and len(high) >= 2:
        new_lead_status = "POTENTIAL_RESEARCH_LEAD"
        summary = "Trace found multiple non-official/high-relevance public results worth deeper public-source review."
    if alias_hits and len(non_official) >= 1:
        new_lead_status = "POTENTIAL_ALIAS_LEAD"
        summary = "Trace found alias-linked public evidence that may deserve corroboration."
    if not public_results:
        new_lead_status = "NO_RESULTS"
        summary = "Trace found no public search results for the selected hypotheses."
    return {
        "case_id": case["case_id"],
        "generated_at": now_iso(),
        "new_lead_status": new_lead_status,
        "summary": summary,
        "result_count": len(public_results),
        "official_result_count": len(official),
        "non_official_result_count": len(non_official),
        "high_relevance_count": len(high),
        "alias_hits": alias_hits,
        "domains": domains,
        "by_hypothesis": by_hyp_json,
        "recommended_next": "Run deeper public evidence capture on POTENTIAL_* hypotheses; otherwise continue official/court-record route.",
        "external_actions_performed": False,
    }


def cmd_run_hypotheses(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    hyp_path = Path(args.hypotheses) if args.hypotheses else OUTPUTS / case_id / "hypotheses" / "lead-hypotheses.json"
    if not hyp_path.exists():
        raise SystemExit(f"Hypotheses file not found: {hyp_path}. Run hypotheses first.")
    hyp_payload = read_json(hyp_path)
    hypotheses = hyp_payload.get("hypotheses", [])
    if args.hypothesis_id:
        hypotheses = [h for h in hypotheses if h.get("hypothesis_id") == args.hypothesis_id]
    else:
        hypotheses = sorted(hypotheses, key=lambda h: h.get("priority_score", 0), reverse=True)[: args.top]
    trace_id = args.trace_id or f"trace-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    trace_dir = EVIDENCE / case_id / "traces" / trace_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_ledger = trace_dir / "trace-ledger.jsonl"
    global_ledger = EVIDENCE / case_id / "captures" / "evidence-ledger.jsonl"
    traced_rows: list[dict[str, Any]] = []
    queries_run = 0
    blocked_queries = 0
    for h in hypotheses:
        # Always trace the evidence basis for the hypothesis so the run has a reproducible starting point
        # even when search engines throttle automated HTML requests.
        for basis_rank, basis_url in enumerate(h.get("evidence_basis", [])[: args.max_basis_per_hypothesis], 1):
            result = {"title": basis_url, "url": basis_url, "snippet": h.get("rationale", "")}
            rel = evidence_relevance_score(case, result)
            row = {
                "case_id": case_id,
                "trace_id": trace_id,
                "kind": "hypothesis_basis_result",
                "hypothesis_id": h.get("hypothesis_id"),
                "hypothesis_title": h.get("title"),
                "hypothesis_priority_score": h.get("priority_score"),
                "query": "evidence_basis",
                "query_risk": "low",
                "rank": basis_rank,
                "title": result["title"],
                "url": basis_url,
                "domain": source_domain(basis_url),
                "snippet": redact_sensitive_lines(result["snippet"]),
                "captured_at": now_iso(),
                "url_sha256": sha256_text(basis_url),
                "snippet_sha256": sha256_text(result["snippet"]),
                "official_domain": is_official_domain(basis_url),
                "relevance_score": rel["score"],
                "relevance_reasons": rel["reasons"] + ["hypothesis evidence basis"],
                "alias_hits": rel["alias_hits"],
                "page_fetch": {"fetched": False, "reason": "basis_trace_only"},
                "external_actions_performed": False,
                "policy": "hypothesis runner: public evidence basis only; no contact/submission/private data",
            }
            append_jsonl(trace_ledger, row)
            append_jsonl(global_ledger, row)
            traced_rows.append(row)
        allowed_queries = [q for q in h.get("allowed_queries", []) if q.get("allowed", True)]
        blocked_queries += len([q for q in h.get("allowed_queries", []) if not q.get("allowed", True)])
        if args.max_queries_per_hypothesis:
            allowed_queries = allowed_queries[: args.max_queries_per_hypothesis]
        for q in allowed_queries:
            query = q["query"]
            queries_run += 1
            results = ddg_search(query, limit=args.per_query)
            if not results:
                row = {
                    "case_id": case_id,
                    "trace_id": trace_id,
                    "kind": "hypothesis_search_no_results",
                    "hypothesis_id": h.get("hypothesis_id"),
                    "hypothesis_title": h.get("title"),
                    "query": query,
                    "captured_at": now_iso(),
                    "external_actions_performed": False,
                }
                append_jsonl(trace_ledger, row)
                traced_rows.append(row)
            for rank, result in enumerate(results, 1):
                captured_at = now_iso()
                if result.get("title") == "SEARCH_ERROR":
                    row = {
                        "case_id": case_id,
                        "trace_id": trace_id,
                        "kind": "hypothesis_search_error",
                        "hypothesis_id": h.get("hypothesis_id"),
                        "hypothesis_title": h.get("title"),
                        "query": query,
                        "error": result.get("snippet"),
                        "captured_at": captured_at,
                        "external_actions_performed": False,
                    }
                    append_jsonl(trace_ledger, row)
                    traced_rows.append(row)
                    continue
                rel = evidence_relevance_score(case, result)
                page = safe_fetch_excerpt(result.get("url", ""), max_chars=args.excerpt_chars) if args.fetch_pages else {"fetched": False, "reason": "fetch_pages_disabled"}
                row = {
                    "case_id": case_id,
                    "trace_id": trace_id,
                    "kind": "hypothesis_search_result",
                    "hypothesis_id": h.get("hypothesis_id"),
                    "hypothesis_title": h.get("title"),
                    "hypothesis_priority_score": h.get("priority_score"),
                    "query": query,
                    "query_risk": q.get("risk", "low"),
                    "rank": rank,
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "domain": source_domain(result.get("url", "")),
                    "snippet": redact_sensitive_lines(result.get("snippet", "")),
                    "captured_at": captured_at,
                    "url_sha256": sha256_text(result.get("url", "")),
                    "snippet_sha256": sha256_text(result.get("snippet", "")),
                    "official_domain": is_official_domain(result.get("url", "")),
                    "relevance_score": rel["score"],
                    "relevance_reasons": rel["reasons"],
                    "alias_hits": rel["alias_hits"],
                    "page_fetch": page,
                    "external_actions_performed": False,
                    "policy": "hypothesis runner: public search only; no contact/submission/private data",
                }
                append_jsonl(trace_ledger, row)
                append_jsonl(global_ledger, row)
                traced_rows.append(row)
            time.sleep(args.delay)
    analysis = analyze_trace_for_leads(case, traced_rows, hypotheses)
    write_json(trace_dir / "lead-trace-analysis.json", analysis)
    lines = [
        f"# Lead Trace Analysis — {case_id} / {trace_id}",
        "",
        f"- Generated: {analysis['generated_at']}",
        f"- Status: {analysis['new_lead_status']}",
        f"- Summary: {analysis['summary']}",
        f"- Results: {analysis['result_count']}",
        f"- Official: {analysis['official_result_count']}",
        f"- Non-official: {analysis['non_official_result_count']}",
        f"- High relevance: {analysis['high_relevance_count']}",
        f"- Domains: {', '.join(analysis['domains']) or 'none'}",
        f"- Alias hits: {', '.join(analysis['alias_hits']) or 'none'}",
        f"- External actions performed: {analysis['external_actions_performed']}",
        "",
        "## By hypothesis",
        "",
    ]
    for hid, stats in analysis["by_hypothesis"].items():
        lines += [f"### `{hid}`", f"- Results: {stats['results']}", f"- High relevance: {stats['high_relevance']}", f"- Official: {stats['official']}", f"- Domains: {', '.join(stats['domains']) or 'none'}", ""]
    (trace_dir / "lead-trace-analysis.md").write_text("\n".join(lines))
    memory_entry = {
        "ran_at": now_iso(),
        "trace_id": trace_id,
        "hypotheses_run": [h.get("hypothesis_id") for h in hypotheses],
        "queries_run": queries_run,
        "blocked_queries_skipped": blocked_queries,
        "results_captured": analysis["result_count"],
        "lead_analysis": analysis,
        "external_actions_performed": False,
    }
    memory_path = update_case_memory(case, memory_entry)
    # Refresh graph-score and hypotheses if requested.
    refreshed: dict[str, Any] = {}
    if args.refresh:
        rows = read_jsonl(global_ledger)
        entities, edges, metrics = build_entity_graph(case, rows)
        assessment = confidence_assessment(case, metrics, rows)
        graph_dir = OUTPUTS / case_id / "graph-score"
        graph_dir.mkdir(parents=True, exist_ok=True)
        write_json(graph_dir / "entities.json", entities)
        write_json(graph_dir / "edges.json", edges)
        write_json(graph_dir / "confidence-score.json", assessment)
        (graph_dir / "confidence-score.md").write_text(f"# Entity Graph + Confidence Score — {case_id}\n\n- Research confidence: {assessment['research_confidence_score']}\n- Verdict: {assessment['verdict']}\n- Tip readiness: {assessment['tip_readiness']}\n- External actions performed: false\n")
        new_hypotheses = hypothesis_templates(case, assessment, rows)
        hyp_dir = OUTPUTS / case_id / "hypotheses"
        hyp_dir.mkdir(parents=True, exist_ok=True)
        write_json(hyp_dir / "lead-hypotheses.json", {"case_id": case_id, "generated_at": now_iso(), "hypothesis_count": len(new_hypotheses), "hypotheses": new_hypotheses, "external_actions_performed": False})
        refreshed = {"graph_score": str(graph_dir / "confidence-score.json"), "hypotheses": str(hyp_dir / "lead-hypotheses.json")}
    case.setdefault("traces", {})["latest"] = str((trace_dir / "lead-trace-analysis.json").relative_to(ROOT))
    case.setdefault("memory", {})["path"] = str(memory_path.relative_to(ROOT))
    save_case(case)
    print(json.dumps({
        "case_id": case_id,
        "trace_id": trace_id,
        "hypotheses_run": len(hypotheses),
        "queries_run": queries_run,
        "results_captured": analysis["result_count"],
        "new_lead_status": analysis["new_lead_status"],
        "trace_dir": str(trace_dir),
        "case_memory": str(memory_path),
        "refreshed": refreshed,
        "external_actions_performed": False,
    }, indent=2, ensure_ascii=False))


def load_case_artifacts(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    ledger = read_jsonl(EVIDENCE / case_id / "captures" / "evidence-ledger.jsonl")
    score_path = OUTPUTS / case_id / "graph-score" / "confidence-score.json"
    hypotheses_path = OUTPUTS / case_id / "hypotheses" / "lead-hypotheses.json"
    memory_path = CASES / case_id / "case-memory.json"
    return {
        "ledger": ledger,
        "score": read_json(score_path) if score_path.exists() else {},
        "hypotheses": read_json(hypotheses_path) if hypotheses_path.exists() else {},
        "memory": read_json(memory_path) if memory_path.exists() else {},
    }


def evidence_table_rows(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    public_rows = [r for r in rows if r.get("kind") in {"public_search_result", "hypothesis_search_result", "hypothesis_basis_result"}]
    public_rows.sort(key=lambda r: (int(r.get("relevance_score") or 0), bool(r.get("official_domain"))), reverse=True)
    seen: set[str] = set()
    out = []
    for r in public_rows:
        url = r.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({
            "title": r.get("title", ""),
            "url": url,
            "domain": r.get("domain") or source_domain(url),
            "official": bool(r.get("official_domain")),
            "relevance_score": int(r.get("relevance_score") or 0),
            "captured_at": r.get("captured_at", ""),
            "snippet": r.get("snippet", "")[:280],
        })
        if len(out) >= limit:
            break
    return out


def draft_tip_packet(case: dict[str, Any], artifacts: dict[str, Any], *, mode: str = "research-summary") -> str:
    entity = (case.get("entities") or [{}])[0]
    score = artifacts.get("score") or {}
    hypotheses = (artifacts.get("hypotheses") or {}).get("hypotheses", [])
    memory = artifacts.get("memory") or {}
    latest_run = (memory.get("runs") or [{}])[-1] if memory.get("runs") else {}
    lead_analysis = latest_run.get("lead_analysis", {}) if latest_run else {}
    rows = evidence_table_rows(artifacts.get("ledger") or [], limit=14)
    official_channels = case.get("official_channels") or []
    submission_gate = f"APPROVE SUBMISSION: {case.get('case_id')} to <official channel>"
    lines = [
        f"# Tip Packet Draft — {case.get('title')}",
        "",
        "**Status: DRAFT ONLY — NOT SUBMITTED**",
        "",
        f"- Case ID: `{case.get('case_id')}`",
        f"- Draft mode: `{mode}`",
        f"- Generated: {now_iso()}",
        f"- External actions performed: false",
        f"- Research confidence: {score.get('research_confidence_score', 'n/a')}",
        f"- Verdict: {score.get('verdict', 'n/a')}",
        f"- Tip readiness: {score.get('tip_readiness', 'n/a')}",
        "",
        "## Executive assessment",
        "",
    ]
    if score.get("tip_readiness") == "NOT_READY_NEW_LEAD":
        lines += [
            "This packet does **not** currently contain a new actionable tip. It confirms and organizes official/public information and identifies lawful next research routes.",
            "",
        ]
    else:
        lines += [
            "This packet requires human/legal review before any external submission. Treat all findings as research leads, not accusations.",
            "",
        ]
    lines += [
        "## Subject / official notice data",
        "",
        f"- Name: {entity.get('name')}",
        f"- Aliases: {', '.join(entity.get('aliases') or []) or 'none extracted'}",
        f"- Allegation/notice basis: {entity.get('allegation') or '; '.join(case.get('allegations') or [])}",
        f"- Reward amount: ${case.get('reward_amount_usd'):,}" if case.get("reward_amount_usd") else "- Reward amount: unknown",
        f"- Official source: {case.get('source', {}).get('official_url') or case.get('source', {}).get('url')}",
        f"- Source legitimacy: {case.get('source', {}).get('legitimacy', 'unknown')}",
        "",
        "## Official channels extracted",
        "",
    ]
    if official_channels:
        for ch in official_channels:
            lines.append(f"- {ch.get('type')}: `{ch.get('value')}` ({ch.get('agency')})")
    else:
        lines.append("- none extracted")
    lines += [
        "",
        "## What is verified",
        "",
    ]
    verified = []
    if case.get("source", {}).get("legitimacy") == "verified_official":
        verified.append("The public reward notice was verified against an official government domain/source.")
    if score.get("metrics", {}).get("source_counts", {}).get("official", 0):
        verified.append(f"Official-source evidence rows found: {score.get('metrics', {}).get('source_counts', {}).get('official')}")
    if score.get("metrics", {}).get("source_counts", {}).get("public", 0):
        verified.append(f"Non-official public-source evidence rows found: {score.get('metrics', {}).get('source_counts', {}).get('public')}")
    lines += [f"- {v}" for v in verified] or ["- No verified claims yet."]
    lines += [
        "",
        "## What is not known / not claimed",
        "",
        "- No current location is identified by this packet.",
        "- No new associate, co-conspirator, wallet, account, address, phone, or private identifier is claimed as a tip.",
        "- No private databases, leaked data, or contacted sources were used.",
        "- No external submission has been made.",
        "",
        "## Latest lead trace analysis",
        "",
        f"- Status: {lead_analysis.get('new_lead_status', 'n/a')}",
        f"- Summary: {lead_analysis.get('summary', 'No trace analysis available.')}",
        f"- Results captured: {lead_analysis.get('result_count', 'n/a')}",
        f"- Domains: {', '.join(lead_analysis.get('domains') or []) or 'n/a'}",
        "",
        "## Evidence table",
        "",
        "| # | Source | Official | Relevance | Captured | Notes |",
        "|---|---|---:|---:|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        title = (r["title"] or r["domain"] or r["url"]).replace("|", "/")[:90]
        notes = (r["snippet"] or "").replace("|", "/").replace("\n", " ")[:160]
        lines.append(f"| {i} | [{title}]({r['url']}) | {str(r['official']).lower()} | {r['relevance_score']} | {r['captured_at']} | {notes} |")
    if not rows:
        lines.append("| - | No evidence rows available | - | - | - | - |")
    lines += [
        "",
        "## Recommended next research paths",
        "",
    ]
    for h in hypotheses[:5]:
        lines += [
            f"### {h.get('priority_score')} — {h.get('title')}",
            f"- ID: `{h.get('hypothesis_id')}`",
            f"- Rationale: {h.get('rationale')}",
            "- Allowed queries:",
        ]
        for q in (h.get("allowed_queries") or [])[:5]:
            lines.append(f"  - `{q.get('query')}`")
        lines += ["- Blocked paths:"]
        for b in (h.get("blocked_paths") or [])[:4]:
            lines.append(f"  - {b}")
        lines.append("")
    lines += [
        "## Submission gate",
        "",
        "This draft must not be submitted externally unless Harvey reviews the final packet and gives the exact approval phrase:",
        "",
        f"`{submission_gate}`",
        "",
        "Generic approvals, checkmarks, or prior local approvals are not enough for external tip submission.",
        "",
        "## Policy footer",
        "",
        "Public-source research only. No contact. No doxxing. No hacking. No leaked/private data. No external submission performed.",
        "",
    ]
    return "\n".join(lines)


def cmd_tip_packet(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    artifacts = load_case_artifacts(case)
    packet = draft_tip_packet(case, artifacts, mode=args.mode)
    outdir = OUTPUTS / case["case_id"] / "tip-packet"
    outdir.mkdir(parents=True, exist_ok=True)
    packet_path = outdir / "tip-packet-draft.md"
    packet_path.write_text(packet)
    manifest = {
        "case_id": case["case_id"],
        "generated_at": now_iso(),
        "mode": args.mode,
        "packet": str(packet_path.relative_to(ROOT)),
        "external_actions_performed": False,
        "submitted": False,
        "submission_requires_exact_phrase": f"APPROVE SUBMISSION: {case['case_id']} to <official channel>",
    }
    write_json(outdir / "tip-packet-manifest.json", manifest)
    case.setdefault("tip_packet", {})["latest"] = str(packet_path.relative_to(ROOT))
    save_case(case)
    print(json.dumps({
        "case_id": case["case_id"],
        "packet": str(packet_path),
        "manifest": str(outdir / "tip-packet-manifest.json"),
        "external_actions_performed": False,
        "submitted": False,
    }, indent=2, ensure_ascii=False))


def safe_username_candidates(case: dict[str, Any]) -> list[dict[str, Any]]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    aliases = entity.get("aliases") or []
    candidates: list[dict[str, Any]] = []
    def add(value: str, source: str, allowed: bool, reason: str, risk: str = "medium") -> None:
        value = re.sub(r"[^A-Za-z0-9_.-]", "", value.strip())
        if not value:
            return
        if value.lower() not in {c["username"].lower() for c in candidates}:
            candidates.append({"username": value, "source": source, "allowed": allowed, "reason": reason, "risk": risk})
    for alias in aliases:
        compact = re.sub(r"\s+", "", alias)
        if len(compact) < 4:
            add(compact, "official_alias", False, "alias too short/common; high false-positive risk", "high")
        else:
            add(compact, "official_alias", True, "official alias, long enough for public username correlation", "medium")
            if " " in alias:
                add(alias.replace(" ", "_"), "official_alias_variant", True, "underscore variant of official alias", "medium")
                add(alias.replace(" ", "."), "official_alias_variant", True, "dot variant of official alias", "medium")
    if name:
        parts = [x for x in re.split(r"\s+", name) if x]
        if len(parts) >= 2:
            add("".join(parts), "primary_name_variant", True, "primary-name compact variant; corroboration only", "medium")
            add(".".join(parts), "primary_name_variant", True, "primary-name dot variant; corroboration only", "medium")
    return candidates


def cmd_sherlock_plan(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    candidates = safe_username_candidates(case)
    if args.allowed_only:
        candidates = [c for c in candidates if c["allowed"]]
    outdir = OUTPUTS / case_id / "sherlock-plan"
    outdir.mkdir(parents=True, exist_ok=True)
    tool = {
        "name": "sherlock-project/sherlock",
        "url": "https://github.com/sherlock-project/sherlock",
        "license": "MIT",
        "audited_commit": "4e2a4f6",
        "purpose": "Username presence checks across public sites for officially published aliases only.",
        "policy": "Correlation only. No contact, no login, no harassment, no accusation, no external submission.",
    }
    allowed = [c for c in candidates if c["allowed"]]
    command_preview = []
    if allowed:
        usernames = " ".join(c["username"] for c in allowed[: args.limit or len(allowed)])
        command_preview.append(f"sherlock {usernames} --print-found --timeout 20 --folderoutput <case-sherlock-output>")
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "tool": tool,
        "candidates": candidates[: args.limit] if args.limit else candidates,
        "allowed_count": sum(1 for c in candidates if c["allowed"]),
        "blocked_count": sum(1 for c in candidates if not c["allowed"]),
        "command_preview": command_preview,
        "external_actions_performed": False,
        "executed_sherlock": False,
        "blocked_paths": [
            "Do not contact discovered accounts",
            "Do not treat username match as identity proof",
            "Do not search private phone/address/relatives",
            "Do not use --browse to open/contact profiles automatically",
            "Do not submit tips based only on Sherlock matches",
        ],
    }
    write_json(outdir / "sherlock-plan.json", payload)
    lines = [
        f"# Sherlock Username Correlation Plan — {case_id}",
        "",
        "- Tool: `sherlock-project/sherlock`",
        "- Mode: plan only; not executed",
        "- External actions performed: false",
        "- Purpose: public username correlation for officially published aliases only",
        "",
        "## Candidates",
        "",
    ]
    for c in payload["candidates"]:
        mark = "ALLOW" if c["allowed"] else "BLOCK"
        lines.append(f"- **{mark}** `{c['username']}` — {c['reason']} (risk: {c['risk']})")
    lines += ["", "## Command preview", ""]
    lines += [f"```bash\n{cmd}\n```" for cmd in command_preview] or ["No allowed usernames."]
    lines += ["", "## Blocked paths", ""]
    lines += [f"- {b}" for b in payload["blocked_paths"]]
    (outdir / "sherlock-plan.md").write_text("\n".join(lines) + "\n")
    case.setdefault("tools", {})["sherlock_plan"] = str((outdir / "sherlock-plan.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({
        "case_id": case_id,
        "allowed": payload["allowed_count"],
        "blocked": payload["blocked_count"],
        "outdir": str(outdir),
        "external_actions_performed": False,
        "executed_sherlock": False,
    }, indent=2, ensure_ascii=False))


def load_text_if_exists(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def extract_court_clues(case: dict[str, Any], ledger_rows: list[dict[str, Any]]) -> dict[str, Any]:
    case_id = case["case_id"]
    source_excerpt = load_text_if_exists(OUTPUTS / case_id / "source-check" / "source-excerpt-redacted.txt")
    haystack = "\n".join([
        case.get("raw_text", ""),
        source_excerpt,
        "\n".join(f"{r.get('title','')} {r.get('snippet','')} {r.get('url','')}" for r in ledger_rows),
    ])
    clues: dict[str, Any] = {
        "districts": sorted(set(re.findall(r"Central District of California|C\.D\. Cal\.?|CDCA", haystack, re.I))),
        "sentencing_dates": sorted(set(re.findall(r"(?:sentenced|sentencing).*?(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}", haystack, re.I))),
        "money_amounts": sorted(set(re.findall(r"\$\s?\d+(?:\.\d+)?\s?(?:million|billion|M|B)?", haystack, re.I))),
        "case_numbers": sorted(set(re.findall(r"\b(?:CR|cr|No\.|Case(?:\s+No\.)?)\s*[:#]?\s*\d{2,4}[-:]?\d{2,6}(?:[-A-Z0-9]+)?\b", haystack))),
        "legal_terms": sorted(set(term for term in ["plea agreement", "sentenced", "convicted", "indictment", "forfeiture", "shell companies", "wire transfers", "bank accounts", "cryptocurrency scams"] if re.search(re.escape(term), haystack, re.I))),
    }
    official_justice_urls = sorted({r.get("url") for r in ledger_rows if r.get("kind") in {"public_search_result", "hypothesis_search_result", "hypothesis_basis_result"} and "justice.gov" in (r.get("domain") or source_domain(r.get("url", "")))})
    clues["official_justice_urls"] = official_justice_urls
    return clues


def court_deepening_queries(case: dict[str, Any], clues: dict[str, Any]) -> list[dict[str, Any]]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    queries: list[dict[str, Any]] = []
    def add(query: str, purpose: str, source_class: str = "public", risk: str = "low") -> None:
        queries.append({"query": query, "purpose": purpose, "source_class": source_class, "risk": risk, "allowed": True})
    add(f'"{name}" "Central District of California"', "Locate official district/case context", "official")
    add(f'"{name}" "United States v"', "Find case caption or public docket references", "public")
    add(f'"{name}" "plea agreement"', "Find plea documents or summaries", "public")
    add(f'"{name}" "sentenced" "20 years"', "Find sentencing releases and summaries", "public")
    add(f'"{name}" "73.6 million"', "Corroborate amount and forfeiture/loss context", "public")
    add(f'"{name}" "shell companies" "bank accounts"', "Identify publicly named shell-company context", "public")
    add(f'"{name}" site:justice.gov', "Official DOJ references", "official")
    add(f'"{name}" site:cacd.uscourts.gov', "Official court-domain references", "official")
    add(f'"{name}" site:govinfo.gov', "Official public filings/opinions if available", "official")
    add(f'"{name}" site:storage.courtlistener.com', "Public RECAP/court document mirror references", "public")
    for cn in clues.get("case_numbers") or []:
        add(f'"{cn}" "{name}"', "Follow extracted case number", "public")
    return queries


def court_depth_assessment(clues: dict[str, Any], captured: list[dict[str, Any]]) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    blockers: list[str] = []
    if clues.get("official_justice_urls"):
        score += 25; reasons.append("official DOJ URLs present")
    if clues.get("districts"):
        score += 15; reasons.append("court district identified")
    if clues.get("sentencing_dates"):
        score += 10; reasons.append("sentencing date found")
    if clues.get("money_amounts"):
        score += 10; reasons.append("loss/reward amounts found")
    terms = clues.get("legal_terms") or []
    if "shell companies" in terms or "bank accounts" in terms:
        score += 10; reasons.append("shell-company/bank-account angle present")
    if clues.get("case_numbers"):
        score += 20; reasons.append("case number extracted")
    else:
        blockers.append("case number not extracted yet")
    official_captured = [r for r in captured if r.get("official_domain")]
    if official_captured:
        score += min(10, len(official_captured) * 3); reasons.append("deepening captured official-domain results")
    if not captured:
        blockers.append("search capture produced no new result rows")
    if score >= 75 and clues.get("case_numbers"):
        status = "DOCKET_PATH_READY"
    elif score >= 55:
        status = "CASE_CONTEXT_FOUND_NOT_DOCKET"
    else:
        status = "COURT_CONTEXT_INCOMPLETE"
    return {
        "court_depth_score": min(score, 100),
        "status": status,
        "reasons": reasons,
        "blockers": blockers,
        "external_actions_performed": False,
    }


def cmd_court_deepen(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    ledger_path = Path(args.ledger) if args.ledger else EVIDENCE / case_id / "captures" / "evidence-ledger.jsonl"
    ledger_rows = read_jsonl(ledger_path)
    clues = extract_court_clues(case, ledger_rows)
    queries = court_deepening_queries(case, clues)
    if args.max_queries:
        queries = queries[: args.max_queries]
    outdir = OUTPUTS / case_id / "court-deepening"
    outdir.mkdir(parents=True, exist_ok=True)
    trace_dir = EVIDENCE / case_id / "court-deepening"
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_ledger = trace_dir / "court-deepening-ledger.jsonl"
    captured: list[dict[str, Any]] = []
    # Always trace official DOJ basis URLs already found.
    for url in clues.get("official_justice_urls") or []:
        row = {
            "case_id": case_id,
            "kind": "court_official_basis",
            "url": url,
            "domain": source_domain(url),
            "title": url,
            "captured_at": now_iso(),
            "official_domain": is_official_domain(url),
            "relevance_score": 60,
            "external_actions_performed": False,
            "policy": "official/public court deepening basis; no contact/private data",
        }
        append_jsonl(trace_ledger, row)
        captured.append(row)
    queries_run = 0
    if args.run_search:
        for q in queries:
            queries_run += 1
            results = ddg_search(q["query"], limit=args.per_query)
            if not results:
                append_jsonl(trace_ledger, {"case_id": case_id, "kind": "court_search_no_results", "query": q["query"], "captured_at": now_iso(), "external_actions_performed": False})
            for rank, result in enumerate(results, 1):
                if result.get("title") == "SEARCH_ERROR":
                    append_jsonl(trace_ledger, {"case_id": case_id, "kind": "court_search_error", "query": q["query"], "error": result.get("snippet"), "captured_at": now_iso(), "external_actions_performed": False})
                    continue
                rel = evidence_relevance_score(case, result)
                row = {
                    "case_id": case_id,
                    "kind": "court_search_result",
                    "query": q["query"],
                    "query_purpose": q["purpose"],
                    "rank": rank,
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "domain": source_domain(result.get("url", "")),
                    "snippet": redact_sensitive_lines(result.get("snippet", "")),
                    "captured_at": now_iso(),
                    "official_domain": is_official_domain(result.get("url", "")),
                    "relevance_score": rel["score"],
                    "relevance_reasons": rel["reasons"],
                    "external_actions_performed": False,
                    "policy": "court deepening: public/official sources only; no contact/private data",
                }
                append_jsonl(trace_ledger, row)
                append_jsonl(ledger_path, row)
                captured.append(row)
            time.sleep(args.delay)
    assessment = court_depth_assessment(clues, captured)
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "queries": queries,
        "queries_run": queries_run,
        "clues": clues,
        "assessment": assessment,
        "captured_count": len(captured),
        "trace_ledger": str(trace_ledger.relative_to(ROOT)),
        "external_actions_performed": False,
        "blocked_paths": [
            "Do not access sealed filings",
            "Do not buy private database records",
            "Do not contact victims, witnesses, co-defendants, relatives, employers, or alleged associates",
            "Do not submit tips based only on court-context corroboration",
        ],
    }
    write_json(outdir / "court-deepening.json", payload)
    lines = [
        f"# Court Records Deepening — {case_id}",
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Court depth score: {assessment['court_depth_score']}",
        f"- Status: {assessment['status']}",
        f"- Queries run: {queries_run}",
        f"- Captured rows: {len(captured)}",
        "- External actions performed: false",
        "",
        "## Clues",
        "",
        "```json",
        json.dumps(clues, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Reasons",
        "",
    ]
    lines += [f"- {r}" for r in assessment["reasons"]] or ["- none"]
    lines += ["", "## Blockers", ""]
    lines += [f"- {b}" for b in assessment["blockers"]] or ["- none"]
    lines += ["", "## Safe court queries", ""]
    for q in queries:
        lines.append(f"- `{q['query']}` — {q['purpose']}")
    lines += ["", "## Blocked paths", ""]
    lines += [f"- {b}" for b in payload["blocked_paths"]]
    (outdir / "court-deepening.md").write_text("\n".join(lines) + "\n")
    case.setdefault("court_deepening", {})["latest"] = str((outdir / "court-deepening.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({
        "case_id": case_id,
        "court_depth_score": assessment["court_depth_score"],
        "status": assessment["status"],
        "captured_count": len(captured),
        "queries_run": queries_run,
        "outdir": str(outdir),
        "external_actions_performed": False,
    }, indent=2, ensure_ascii=False))


def docket_candidate_score(case: dict[str, Any], result: dict[str, str]) -> dict[str, Any]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    haystack = f"{result.get('title','')} {result.get('snippet','')} {result.get('url','')}"
    score = 0
    reasons: list[str] = []
    if name and re.search(re.escape(name), haystack, re.I):
        score += 30; reasons.append("primary name match")
    if re.search(r"United States v\.?|case(?:\s+no\.)?|criminal|docket|plea|sentenc|indictment", haystack, re.I):
        score += 25; reasons.append("docket/court terms")
    if re.search(r"Central District of California|C\.D\. Cal\.?|CDCA|cacd", haystack, re.I):
        score += 20; reasons.append("CDCA court/district signal")
    if re.search(r"\b\d{2}-cr-\d+|\bCR\s*\d{2,}|case\s+no", haystack, re.I):
        score += 20; reasons.append("case-number-like pattern")
    domain = source_domain(result.get("url", ""))
    if domain in {"justice.gov", "cacd.uscourts.gov", "govinfo.gov"} or domain.endswith(".uscourts.gov"):
        score += 20; reasons.append("official court/government domain")
    elif domain in {"courtlistener.com", "storage.courtlistener.com", "recap.email"}:
        score += 15; reasons.append("public RECAP/court mirror domain")
    elif domain:
        score += 3; reasons.append("public web source")
    return {"score": min(score, 100), "reasons": reasons}


def docket_finder_queries(case: dict[str, Any], clues: dict[str, Any]) -> list[dict[str, Any]]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    queries: list[dict[str, Any]] = []
    def add(query: str, purpose: str, risk: str = "low") -> None:
        queries.append({"query": query, "purpose": purpose, "risk": risk, "allowed": True})
    add(f'"{name}" "United States v."', "Find case caption")
    add(f'"{name}" "United States v" "Central District of California"', "Find CDCA case caption")
    add(f'"{name}" "case no"', "Find public case number references")
    add(f'"{name}" "criminal complaint"', "Find charging document references")
    add(f'"{name}" "plea agreement" filetype:pdf', "Find public plea agreement PDFs")
    add(f'"{name}" "sentencing memorandum"', "Find sentencing filing references")
    add(f'"{name}" site:cacd.uscourts.gov', "Official CDCA court website")
    add(f'"{name}" site:govinfo.gov', "Official govinfo court/opinion records")
    add(f'"{name}" site:storage.courtlistener.com', "Public RECAP document mirror")
    add(f'"{name}" site:recap.email', "Public RECAP archive")
    for cn in clues.get("case_numbers") or []:
        add(f'"{cn}" "{name}"', "Follow extracted case number")
    return queries


def extract_case_number_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    haystack = "\n".join(f"{r.get('title','')} {r.get('snippet','')} {r.get('url','')}" for r in rows)
    patterns = [
        r"\b\d{2}-cr-\d{3,6}(?:-[A-Z]+)?\b",
        r"\b\d{2,4}-CR-\d{3,6}(?:-[A-Z]+)?\b",
        r"\bCR\s*\d{2,4}[-:]?\d{3,6}\b",
        r"Case\s+No\.?\s*[:#]?\s*[A-Z0-9:.-]+",
    ]
    nums: set[str] = set()
    for pat in patterns:
        for m in re.findall(pat, haystack, re.I):
            nums.add(re.sub(r"\s+", " ", m).strip())
    return sorted(nums)


def cmd_docket_find(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    ledger_path = Path(args.ledger) if args.ledger else EVIDENCE / case_id / "captures" / "evidence-ledger.jsonl"
    ledger_rows = read_jsonl(ledger_path)
    clues = extract_court_clues(case, ledger_rows)
    queries = docket_finder_queries(case, clues)
    if args.max_queries:
        queries = queries[: args.max_queries]
    outdir = OUTPUTS / case_id / "docket-finder"
    outdir.mkdir(parents=True, exist_ok=True)
    trace_dir = EVIDENCE / case_id / "docket-finder"
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_ledger = trace_dir / "docket-finder-ledger.jsonl"
    rows: list[dict[str, Any]] = []
    queries_run = 0
    for q in queries:
        queries_run += 1
        results = ddg_search(q["query"], limit=args.per_query)
        if not results:
            row = {"case_id": case_id, "kind": "docket_search_no_results", "query": q["query"], "captured_at": now_iso(), "external_actions_performed": False}
            append_jsonl(trace_ledger, row); rows.append(row)
        for rank, result in enumerate(results, 1):
            if result.get("title") == "SEARCH_ERROR":
                row = {"case_id": case_id, "kind": "docket_search_error", "query": q["query"], "error": result.get("snippet"), "captured_at": now_iso(), "external_actions_performed": False}
                append_jsonl(trace_ledger, row); rows.append(row); continue
            score = docket_candidate_score(case, result)
            row = {
                "case_id": case_id,
                "kind": "docket_candidate",
                "query": q["query"],
                "query_purpose": q["purpose"],
                "rank": rank,
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "domain": source_domain(result.get("url", "")),
                "snippet": redact_sensitive_lines(result.get("snippet", "")),
                "captured_at": now_iso(),
                "official_domain": is_official_domain(result.get("url", "")) or source_domain(result.get("url", "")).endswith("uscourts.gov"),
                "docket_candidate_score": score["score"],
                "docket_reasons": score["reasons"],
                "external_actions_performed": False,
                "policy": "docket finder: public/official sources only; no PACER/private/sealed access",
            }
            append_jsonl(trace_ledger, row)
            rows.append(row)
        time.sleep(args.delay)
    candidates = [r for r in rows if r.get("kind") == "docket_candidate"]
    candidates.sort(key=lambda r: r.get("docket_candidate_score", 0), reverse=True)
    case_numbers = sorted(set((clues.get("case_numbers") or []) + extract_case_number_from_rows(candidates)))
    top_score = candidates[0].get("docket_candidate_score", 0) if candidates else 0
    if case_numbers and top_score >= args.threshold:
        status = "DOCKET_CANDIDATE_FOUND"
    elif candidates and top_score >= args.threshold:
        status = "HIGH_CONFIDENCE_DOCKET_PATH_NO_NUMBER"
    elif candidates:
        status = "LOW_CONFIDENCE_DOCKET_CANDIDATES"
    else:
        status = "NO_DOCKET_CANDIDATE_FOUND"
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "status": status,
        "threshold": args.threshold,
        "queries_run": queries_run,
        "candidate_count": len(candidates),
        "case_numbers": case_numbers,
        "top_candidates": candidates[: args.report_limit],
        "trace_ledger": str(trace_ledger.relative_to(ROOT)),
        "external_actions_performed": False,
        "blocked_paths": [
            "Do not use PACER credentials or paid/private docket databases in this worker",
            "Do not access sealed filings",
            "Do not contact court staff, victims, witnesses, defendants, relatives, employers, or associates",
            "Do not submit tips based only on docket candidates",
        ],
    }
    write_json(outdir / "docket-finder.json", payload)
    lines = [
        f"# Court Docket Finder — {case_id}", "",
        f"- Generated: {payload['generated_at']}",
        f"- Status: {status}",
        f"- Queries run: {queries_run}",
        f"- Candidate count: {len(candidates)}",
        f"- Case numbers: {', '.join(case_numbers) or 'none'}",
        "- External actions performed: false", "",
        "## Top candidates", "",
    ]
    for c in payload["top_candidates"]:
        lines += [
            f"### {c.get('docket_candidate_score')} — {c.get('title') or c.get('url')}",
            f"- URL: {c.get('url')}",
            f"- Domain: {c.get('domain')}",
            f"- Query: `{c.get('query')}`",
            f"- Reasons: {', '.join(c.get('docket_reasons') or [])}",
            f"- Snippet: {c.get('snippet')}", "",
        ]
    lines += ["## Blocked paths", ""] + [f"- {b}" for b in payload["blocked_paths"]]
    (outdir / "docket-finder.md").write_text("\n".join(lines) + "\n")
    case.setdefault("docket_finder", {})["latest"] = str((outdir / "docket-finder.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({
        "case_id": case_id,
        "status": status,
        "queries_run": queries_run,
        "candidate_count": len(candidates),
        "case_numbers": case_numbers,
        "outdir": str(outdir),
        "external_actions_performed": False,
    }, indent=2, ensure_ascii=False))


def public_record_routes(case: dict[str, Any], clues: dict[str, Any]) -> list[dict[str, Any]]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    q_name = urllib.parse.quote(f'"{name}"')
    official_url = case.get("source", {}).get("official_url", "")
    routes: list[dict[str, Any]] = []
    def add(source_id: str, label: str, url: str, purpose: str, access: str, status: str, priority: int, notes: str = "", allowed: bool = True):
        routes.append({
            "source_id": source_id,
            "label": label,
            "url": url,
            "purpose": purpose,
            "access": access,
            "status": status,
            "priority": priority,
            "allowed": allowed,
            "notes": notes,
            "blocked_paths": [
                "No private login/PACER credentials in this router",
                "No paid/private databases",
                "No sealed filings",
                "No contact with people/entities",
                "No external tip submission",
            ],
        })
    if official_url:
        add("state-official-notice", "State Department official notice", official_url, "Canonical reward notice / official details", "public_web", "ready", 100)
    add("state-search", "State.gov search", f"https://www.state.gov/?s={urllib.parse.quote(name)}", "Official State Department related pages", "public_web", "ready", 95)
    add("justice-search", "Justice.gov search", f"https://www.justice.gov/search?keys={urllib.parse.quote(name)}", "DOJ press releases and official case context", "public_web", "ready", 92)
    add("justice-cdca", "DOJ CDCA page search", f"https://www.justice.gov/usao-cdca/search?search_api_fulltext={urllib.parse.quote(name)}", "Central District of California official releases", "public_web", "ready", 90)
    add("secretservice-search", "SecretService.gov search", f"https://www.secretservice.gov/search?search={urllib.parse.quote(name)}", "USSS public mentions / wanted references", "public_web", "ready", 84)
    add("cacd-site", "CDCA court site search", f"https://www.cacd.uscourts.gov/search/node/{urllib.parse.quote(name)}", "Official court website references", "public_web", "ready", 82)
    add("govinfo-search", "GovInfo search", f"https://www.govinfo.gov/app/search/%7B%22query%22%3A%22{q_name}%22%7D", "Official public government records/opinions", "public_web", "ready", 78)
    add("courtlistener-web", "CourtListener public web search", f"https://www.courtlistener.com/?q={q_name}", "Public docket/opinion/RECAP search via website", "public_web", "ready", 76, "Use public web only unless API token is configured.")
    add("courtlistener-api", "CourtListener API", f"https://www.courtlistener.com/api/rest/v3/search/?q={q_name}", "Structured public court search API", "api", "blocked_requires_api_token", 70, "Anonymous API returned 403 in prior test; use only with lawful API token and rate limits.", allowed=False)
    add("recap-storage", "RECAP storage targeted search", f"https://www.google.com/search?q={urllib.parse.quote(name + ' site:storage.courtlistener.com')}", "Public RECAP document mirror discovery", "public_search", "ready", 68)
    add("internet-archive", "Internet Archive web search", f"https://archive.org/search?query={urllib.parse.quote(name)}", "Historical public captures / documents", "public_web", "ready", 55)
    add("pacer-private", "PACER private access", "https://pacer.uscourts.gov/", "Federal docket access", "private_or_paid", "blocked_private_or_paid", 0, "Blocked in PistaLab. Requires human/legal decision outside this worker.", allowed=False)
    routes.sort(key=lambda r: r["priority"], reverse=True)
    return routes


def probe_public_route(route: dict[str, Any], timeout: int = 12) -> dict[str, Any]:
    if not route.get("allowed") or route.get("status", "").startswith("blocked"):
        return {"probed": False, "reason": route.get("status"), "external_actions_performed": False}
    url = route.get("url", "")
    if not url.startswith(("http://", "https://")):
        return {"probed": False, "reason": "unsupported_url", "external_actions_performed": False}
    # Avoid probing Google result pages from this worker; they are route pointers, not evidence.
    if "google.com/search" in url:
        return {"probed": False, "reason": "search_pointer_not_probed", "external_actions_performed": False}
    try:
        status, content_type, raw = fetch_public_url(url, timeout=timeout)
        text = strip_html(raw)[:1200]
        return {
            "probed": True,
            "http_status": status,
            "content_type": content_type,
            "excerpt_sha256": sha256_text(text),
            "excerpt_preview": redact_sensitive_lines(text[:400]),
            "external_actions_performed": False,
        }
    except Exception as exc:
        return {"probed": True, "error": str(exc)[:300], "external_actions_performed": False}


def cmd_source_router(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    ledger_path = Path(args.ledger) if args.ledger else EVIDENCE / case_id / "captures" / "evidence-ledger.jsonl"
    ledger_rows = read_jsonl(ledger_path)
    clues = extract_court_clues(case, ledger_rows)
    routes = public_record_routes(case, clues)
    if args.ready_only:
        routes = [r for r in routes if r.get("allowed") and r.get("status") == "ready"]
    if args.limit:
        routes = routes[: args.limit]
    probes = []
    if args.probe:
        for route in routes[: args.probe_limit]:
            probe = probe_public_route(route)
            route["probe"] = probe
            probes.append({"source_id": route["source_id"], **probe})
            time.sleep(args.delay)
    outdir = OUTPUTS / case_id / "source-router"
    outdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "route_count": len(routes),
        "ready_count": sum(1 for r in routes if r.get("allowed") and r.get("status") == "ready"),
        "blocked_count": sum(1 for r in routes if not r.get("allowed") or str(r.get("status", "")).startswith("blocked")),
        "routes": routes,
        "probes": probes,
        "external_actions_performed": False,
        "policy": "Public records routing only. No private/paid/sealed access and no contact/submission.",
    }
    write_json(outdir / "public-records-source-router.json", payload)
    lines = [
        f"# Public Records Source Router — {case_id}", "",
        f"- Generated: {payload['generated_at']}",
        f"- Routes: {payload['route_count']}",
        f"- Ready: {payload['ready_count']}",
        f"- Blocked: {payload['blocked_count']}",
        f"- External actions performed: false", "",
        "## Routes", "",
    ]
    for r in routes:
        mark = "READY" if r.get("allowed") and r.get("status") == "ready" else "BLOCKED"
        lines += [
            f"### {r['priority']} — {mark} — {r['label']}",
            f"- ID: `{r['source_id']}`",
            f"- URL: {r['url']}",
            f"- Purpose: {r['purpose']}",
            f"- Access: {r['access']}",
            f"- Status: {r['status']}",
            f"- Notes: {r.get('notes') or 'none'}",
        ]
        if r.get("probe"):
            lines.append(f"- Probe: `{json.dumps(r['probe'], ensure_ascii=False)[:500]}`")
        lines.append("")
    (outdir / "public-records-source-router.md").write_text("\n".join(lines) + "\n")
    case.setdefault("source_router", {})["latest"] = str((outdir / "public-records-source-router.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({
        "case_id": case_id,
        "routes": payload["route_count"],
        "ready": payload["ready_count"],
        "blocked": payload["blocked_count"],
        "probed": len(probes),
        "outdir": str(outdir),
        "external_actions_performed": False,
    }, indent=2, ensure_ascii=False))


def load_sherlock_plan(case: dict[str, Any], explicit_plan: str = "") -> dict[str, Any]:
    case_id = case["case_id"]
    plan_path = Path(explicit_plan) if explicit_plan else OUTPUTS / case_id / "sherlock-plan" / "sherlock-plan.json"
    if not plan_path.exists():
        raise SystemExit(f"Sherlock plan not found: {plan_path}. Run sherlock-plan first.")
    return read_json(plan_path)


def parse_sherlock_output(text: str, usernames: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current = ""
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        # Sherlock versions vary. Capture lines with URLs and infer username by nearest explicit username or URL path.
        url_match = re.search(r"https?://\S+", raw)
        for u in usernames:
            if re.search(rf"\b{re.escape(u)}\b", raw, re.I):
                current = u
                break
        if url_match:
            url = url_match.group(0).rstrip(")],.;")
            username = current or next((u for u in usernames if re.search(re.escape(u), url, re.I)), "unknown")
            rows.append({
                "username": username,
                "url": url,
                "domain": source_domain(url),
                "raw_line": raw[:500],
            })
    # De-dupe by URL.
    seen = set()
    out = []
    for row in rows:
        if row["url"] in seen:
            continue
        seen.add(row["url"])
        out.append(row)
    return out


def cmd_sherlock_run(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    plan = load_sherlock_plan(case, args.plan)
    candidates = [c for c in plan.get("candidates", []) if c.get("allowed")]
    if args.username:
        requested = {u.lower() for u in args.username}
        candidates = [c for c in candidates if c.get("username", "").lower() in requested]
    if args.limit:
        candidates = candidates[: args.limit]
    usernames = [c["username"] for c in candidates]
    outdir = OUTPUTS / case_id / "sherlock-run"
    outdir.mkdir(parents=True, exist_ok=True)
    evidence_dir = EVIDENCE / case_id / "sherlock-run"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ledger = evidence_dir / "sherlock-ledger.jsonl"
    preview = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "mode": "execute" if args.execute else "preview",
        "usernames": usernames,
        "allowed_candidates": len(usernames),
        "external_actions_performed": False,
        "executed_sherlock": False,
        "gate_required": "--execute --confirm SHERLOCK_PUBLIC_ALIAS_CHECK",
        "policy": "Only officially published aliases/name variants. Correlation only. No contact/browse/submission.",
        "blocked_paths": [
            "Do not contact discovered accounts",
            "Do not use --browse",
            "Do not treat a username match as identity proof",
            "Do not search phone/address/relatives",
            "Do not submit tips based only on Sherlock matches",
        ],
    }
    write_json(outdir / "sherlock-run-preview.json", preview)
    if not usernames:
        print(json.dumps({**preview, "blocked_reason": "no allowed usernames"}, indent=2, ensure_ascii=False))
        return
    if not args.execute:
        print(json.dumps({**preview, "next": "Rerun with --execute --confirm SHERLOCK_PUBLIC_ALIAS_CHECK to run public username correlation."}, indent=2, ensure_ascii=False))
        return
    blockers = []
    if args.confirm != "SHERLOCK_PUBLIC_ALIAS_CHECK":
        blockers.append("missing --confirm SHERLOCK_PUBLIC_ALIAS_CHECK")
    bundled_sherlock = ROOT / "tools" / "sherlock-venv" / "bin" / "sherlock"
    sherlock_bin = shutil.which("sherlock") or (str(bundled_sherlock) if bundled_sherlock.exists() else "")
    if not sherlock_bin:
        blockers.append("sherlock executable not found; install sherlock-project in an isolated environment")
    if args.browse:
        blockers.append("--browse is prohibited by PistaLab policy")
    if blockers:
        result = {**preview, "blocked_reason": "; ".join(blockers)}
        write_json(outdir / "sherlock-run-result.json", result)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    cmd = [sherlock_bin, *usernames, "--print-found", "--timeout", str(args.timeout), "--folderoutput", str(outdir / "raw")]
    if args.site:
        for site in args.site:
            cmd.extend(["--site", site])
    started = now_iso()
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=args.process_timeout)
    raw_stdout = proc.stdout or ""
    raw_stderr = proc.stderr or ""
    (outdir / "sherlock-stdout.txt").write_text(raw_stdout)
    (outdir / "sherlock-stderr.txt").write_text(raw_stderr)
    matches = parse_sherlock_output(raw_stdout + "\n" + raw_stderr, usernames)
    for match in matches:
        row = {
            "case_id": case_id,
            "kind": "sherlock_username_match_weak",
            "username": match["username"],
            "url": match["url"],
            "domain": match["domain"],
            "captured_at": now_iso(),
            "tool": "sherlock-project/sherlock",
            "confidence": "weak_correlation_only",
            "requires_corroboration": True,
            "external_actions_performed": False,
            "policy": "Do not contact. Do not accuse. Do not submit based only on this match.",
        }
        append_jsonl(ledger, row)
    result = {
        **preview,
        "executed_sherlock": True,
        "started_at": started,
        "completed_at": now_iso(),
        "returncode": proc.returncode,
        "match_count": len(matches),
        "ledger": str(ledger.relative_to(ROOT)),
        "stdout": str((outdir / "sherlock-stdout.txt").relative_to(ROOT)),
        "stderr": str((outdir / "sherlock-stderr.txt").relative_to(ROOT)),
        "external_actions_performed": False,
    }
    write_json(outdir / "sherlock-run-result.json", result)
    case.setdefault("tools", {})["sherlock_run"] = str((outdir / "sherlock-run-result.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps(result, indent=2, ensure_ascii=False))


LOW_VALUE_SHERLOCK_DOMAINS = {
    "archiveofourown.org", "audiojungle.net", "chess.com", "duolingo.com", "flipboard.com",
    "flickr.com", "freelancer.com", "steamcommunity.com", "xboxgamertag.com",
    "deviantart.com", "pinterest.com", "disqus.com", "codecademy.com", "codeforces.com",
    "crowdin.com", "dribbble.com", "fosstodon.org", "gallog.dcinside.com", "periscope.tv",
    "replit.com", "trello.com", "tradingview.com", "clubhouse.com", "clapperapp.com",
}

HIGH_SIGNAL_SHERLOCK_DOMAINS = {
    "github.com", "t.me", "telegram.me", "youtube.com", "tiktok.com", "cash.app",
    "account.venmo.com", "medium.com", "about.me", "bsky.app", "behance.net", "carrd.co",
    "carbonmade.com", "linkedin.com", "x.com", "twitter.com", "facebook.com", "instagram.com",
}


def sherlock_username_rarity(username: str, plan: dict[str, Any]) -> str:
    for c in plan.get("candidates", []):
        if c.get("username", "").lower() == username.lower():
            raw = " ".join(str(x) for x in [c.get("risk", ""), c.get("notes", ""), c.get("reason", ""), c.get("source", "")])
            if re.search(r"short|common|generic|false", raw, re.I):
                return "generic_or_high_false_positive"
            if len(username) <= 5 or re.fullmatch(r"[A-Za-z]+Li", username):
                return "generic_or_high_false_positive"
            if re.search(r"alias|official|notice|published", raw, re.I):
                return "official_alias"
    if len(username) <= 5 or re.fullmatch(r"[A-Za-z]+Li", username):
        return "generic_or_high_false_positive"
    if re.search(r"perfect|kg|crypto|wallet", username, re.I):
        return "distinctive_alias"
    return "unknown"


def sherlock_triage_score(row: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    username = row.get("username", "")
    domain = row.get("domain", "")
    url = row.get("url", "")
    score = 0
    reasons: list[str] = []
    rarity = sherlock_username_rarity(username, plan)
    if rarity in {"official_alias", "distinctive_alias"}:
        score += 35; reasons.append(rarity)
    elif rarity == "generic_or_high_false_positive":
        score -= 25; reasons.append("generic/high false-positive username")
    else:
        score += 5; reasons.append("unknown rarity")
    if domain in HIGH_SIGNAL_SHERLOCK_DOMAINS or any(domain.endswith("." + d) for d in HIGH_SIGNAL_SHERLOCK_DOMAINS):
        score += 25; reasons.append("higher-signal platform")
    if domain in LOW_VALUE_SHERLOCK_DOMAINS or any(domain.endswith("." + d) for d in LOW_VALUE_SHERLOCK_DOMAINS):
        score -= 15; reasons.append("low-value/generic platform")
    if re.search(r"cash\.app|venmo|wallet|crypto|telegram|t\.me|github|youtube|tiktok", url, re.I):
        score += 10; reasons.append("finance/comm/dev/social route worth corroborating")
    if re.search(r"xuanli|darenli", username, re.I):
        score -= 15; reasons.append("name-only username collision risk")
    if re.search(r"kgperfect", username, re.I):
        score += 20; reasons.append("distinctive alias from plan")
    score = max(0, min(100, score))
    if score >= 70:
        tier = "A_CORROBORATE_FIRST"
    elif score >= 45:
        tier = "B_REVIEW_IF_TIME"
    else:
        tier = "C_LIKELY_NOISE"
    return {"score": score, "tier": tier, "reasons": reasons, "rarity": rarity}


def cmd_sherlock_triage(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    plan = load_sherlock_plan(case, args.plan)
    ledger_path = Path(args.ledger) if args.ledger else EVIDENCE / case_id / "sherlock-run" / "sherlock-ledger.jsonl"
    rows = read_jsonl(ledger_path)
    triaged: list[dict[str, Any]] = []
    for row in rows:
        scored = sherlock_triage_score(row, plan)
        triaged.append({**row, **scored})
    triaged.sort(key=lambda r: (r.get("score", 0), r.get("username", ""), r.get("domain", "")), reverse=True)
    selected = [r for r in triaged if r.get("score", 0) >= args.threshold]
    outdir = OUTPUTS / case_id / "sherlock-triage"
    outdir.mkdir(parents=True, exist_ok=True)
    by_tier: dict[str, int] = {}
    by_username: dict[str, int] = {}
    for r in triaged:
        by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + 1
        by_username[r["username"]] = by_username.get(r["username"], 0) + 1
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "input_ledger": str(ledger_path.relative_to(ROOT)) if ledger_path.is_relative_to(ROOT) else str(ledger_path),
        "total_matches": len(rows),
        "threshold": args.threshold,
        "selected_count": len(selected),
        "by_tier": by_tier,
        "by_username": by_username,
        "selected_for_corroboration": selected[: args.limit],
        "all_triaged": triaged,
        "external_actions_performed": False,
        "policy": "Sherlock results are weak correlation only. No contact, no browsing, no accusation, no tip submission.",
    }
    write_json(outdir / "sherlock-triage.json", payload)
    lines = [
        f"# Sherlock Triage — {case_id}", "",
        f"- Generated: {payload['generated_at']}",
        f"- Total matches: {len(rows)}",
        f"- Selected for corroboration: {len(selected)}",
        f"- External actions performed: false", "",
        "## Tier counts", "",
    ]
    for k, v in sorted(by_tier.items()):
        lines.append(f"- {k}: {v}")
    lines += ["", "## Selected for corroboration", ""]
    for r in selected[: args.limit]:
        lines += [
            f"### {r['score']} — {r['tier']} — {r.get('username')} @ {r.get('domain')}",
            f"- URL: {r.get('url')}",
            f"- Reasons: {', '.join(r.get('reasons') or [])}",
            "- Required next step: corroborate against official/case facts before treating as a lead.", "",
        ]
    lines += ["## Policy", "", "- Weak correlation only.", "- No contact.", "- No automatic browsing/opening profiles.", "- No tip submission from Sherlock matches alone."]
    (outdir / "sherlock-triage.md").write_text("\n".join(lines) + "\n")
    case.setdefault("tools", {})["sherlock_triage"] = str((outdir / "sherlock-triage.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({
        "case_id": case_id,
        "total_matches": len(rows),
        "selected_for_corroboration": len(selected),
        "by_tier": by_tier,
        "outdir": str(outdir),
        "external_actions_performed": False,
    }, indent=2, ensure_ascii=False))


def cmd_sherlock_corroborate(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    triage_path = Path(args.triage) if args.triage else OUTPUTS / case_id / "sherlock-triage" / "sherlock-triage.json"
    if not triage_path.exists():
        raise SystemExit(f"Sherlock triage not found: {triage_path}. Run sherlock-triage first.")
    triage = read_json(triage_path)
    selected = triage.get("selected_for_corroboration", [])
    usernames = sorted({r.get("username") for r in selected if r.get("username")})
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    case_terms = ["Daren Li", "money laundering", "cryptocurrency", "USSS", "Secret Service", "pig butchering", "shell companies"]
    queries: list[dict[str, str]] = []
    for username in usernames:
        queries.extend([
            {"username": username, "query": f'"{username}" "{name}"', "purpose": "direct case-name corroboration"},
            {"username": username, "query": f'"{username}" "money laundering"', "purpose": "crime-pattern corroboration"},
            {"username": username, "query": f'"{username}" cryptocurrency OR crypto', "purpose": "crypto context corroboration"},
            {"username": username, "query": f'"{username}" "pig butchering"', "purpose": "scam-pattern corroboration"},
            {"username": username, "query": f'"{username}" "Secret Service" OR USSS', "purpose": "law-enforcement context corroboration"},
        ])
    if args.max_queries:
        queries = queries[: args.max_queries]
    outdir = OUTPUTS / case_id / "sherlock-corroboration"
    outdir.mkdir(parents=True, exist_ok=True)
    evidence_dir = EVIDENCE / case_id / "sherlock-corroboration"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ledger = evidence_dir / "sherlock-corroboration-ledger.jsonl"
    rows: list[dict[str, Any]] = []
    for q in queries:
        results = ddg_search(q["query"], limit=args.per_query)
        if not results:
            row = {"case_id": case_id, "kind": "sherlock_corroboration_no_results", **q, "captured_at": now_iso(), "external_actions_performed": False}
            append_jsonl(ledger, row); rows.append(row)
        for rank, result in enumerate(results, 1):
            if result.get("title") == "SEARCH_ERROR":
                row = {"case_id": case_id, "kind": "sherlock_corroboration_error", **q, "error": result.get("snippet"), "captured_at": now_iso(), "external_actions_performed": False}
                append_jsonl(ledger, row); rows.append(row); continue
            text = f"{result.get('title','')} {result.get('snippet','')} {result.get('url','')}"
            hits = []
            for term in [name, "money laundering", "cryptocurrency", "crypto", "pig butchering", "Secret Service", "USSS", "Daren Li"]:
                if term and re.search(re.escape(term), text, re.I):
                    hits.append(term)
            score = 0
            if q["username"].lower() in text.lower(): score += 25
            if name and re.search(re.escape(name), text, re.I): score += 45
            if any(h in hits for h in ["money laundering", "pig butchering", "Secret Service", "USSS"]): score += 25
            if any(h in hits for h in ["cryptocurrency", "crypto"]): score += 10
            row = {
                "case_id": case_id,
                "kind": "sherlock_corroboration_search_result",
                **q,
                "rank": rank,
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "domain": source_domain(result.get("url", "")),
                "snippet": redact_sensitive_lines(result.get("snippet", "")),
                "hits": hits,
                "corroboration_score": min(score, 100),
                "captured_at": now_iso(),
                "external_actions_performed": False,
                "policy": "Search-snippet corroboration only. No profile opening, no contact, no accusation, no tip submission.",
            }
            append_jsonl(ledger, row); rows.append(row)
        time.sleep(args.delay)
    result_rows = [r for r in rows if r.get("kind") == "sherlock_corroboration_search_result"]
    result_rows.sort(key=lambda r: r.get("corroboration_score", 0), reverse=True)
    strong = [r for r in result_rows if r.get("corroboration_score", 0) >= args.strong_threshold]
    if strong:
        status = "CORROBORATION_CANDIDATES_FOUND_REVIEW_REQUIRED"
    elif result_rows:
        status = "NO_STRONG_CORROBORATION_SNIPPETS"
    else:
        status = "NO_CORROBORATION_RESULTS"
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "status": status,
        "usernames": usernames,
        "queries_run": len(queries),
        "result_count": len(result_rows),
        "strong_count": len(strong),
        "top_results": result_rows[: args.limit],
        "ledger": str(ledger.relative_to(ROOT)),
        "external_actions_performed": False,
        "policy": "Sherlock corroboration uses search snippets only; profile opening/contact/submission are blocked.",
    }
    write_json(outdir / "sherlock-corroboration.json", payload)
    lines = [
        f"# Sherlock Corroboration — {case_id}", "",
        f"- Generated: {payload['generated_at']}",
        f"- Status: {status}",
        f"- Usernames: {', '.join(usernames) or 'none'}",
        f"- Queries run: {len(queries)}",
        f"- Results: {len(result_rows)}",
        f"- Strong candidates: {len(strong)}",
        f"- External actions performed: false", "",
        "## Top search-snippet results", "",
    ]
    for r in payload["top_results"]:
        lines += [
            f"### {r.get('corroboration_score')} — {r.get('title') or r.get('url')}",
            f"- Username: {r.get('username')}",
            f"- URL: {r.get('url')}",
            f"- Query: `{r.get('query')}`",
            f"- Hits: {', '.join(r.get('hits') or []) or 'none'}",
            f"- Snippet: {r.get('snippet')}", "",
        ]
    lines += ["## Policy", "", "- No profile opening.", "- No contact.", "- No accusation.", "- No tip submission from username matches alone."]
    (outdir / "sherlock-corroboration.md").write_text("\n".join(lines) + "\n")
    case.setdefault("tools", {})["sherlock_corroboration"] = str((outdir / "sherlock-corroboration.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({
        "case_id": case_id,
        "status": status,
        "usernames": usernames,
        "queries_run": len(queries),
        "result_count": len(result_rows),
        "strong_count": len(strong),
        "outdir": str(outdir),
        "external_actions_performed": False,
    }, indent=2, ensure_ascii=False))


CAMERA_ALLOWED_SOURCE_TYPES = {
    "official_traffic_camera",
    "official_municipal_webcam",
    "official_airport_port_webcam",
    "public_media_livecam",
    "public_webcam_directory",
}

CAMERA_BLOCKED_SOURCE_TYPES = {
    "open_ip_camera",
    "misconfigured_private_camera",
    "residential_camera",
    "workplace_security_camera",
    "shodan_censys_insecam",
    "face_recognition",
    "private_cctv_request",
}


def case_camera_terms(case: dict[str, Any]) -> dict[str, Any]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    aliases = [a for a in (entity.get("aliases") or []) if a and len(a) > 3]
    source_parts = [json.dumps(case, ensure_ascii=False)]
    case_id = case.get("case_id", "")
    if case_id:
        evidence_root = EVIDENCE / case_id
        if evidence_root.exists():
            for fp in evidence_root.rglob("*.jsonl"):
                try:
                    source_parts.append(fp.read_text(errors="ignore")[:50000])
                except Exception:
                    pass
    source_text = "\n".join(source_parts)
    candidate_terms = [
        "Central District of California", "Los Angeles", "California", "Cambodia", "Kingdom of Cambodia",
        "China", "St. Kitts and Nevis", "Dominican Republic", "United States", "El Camino Real",
    ]
    anchors = []
    for term in candidate_terms:
        if re.search(re.escape(term), source_text, re.I):
            anchors.append(term)
    return {"name": name, "aliases": aliases, "anchors": sorted(set(anchors))}


def public_camera_routes(case: dict[str, Any]) -> list[dict[str, Any]]:
    terms = case_camera_terms(case)
    anchors = terms["anchors"] or ["case location unknown"]
    routes: list[dict[str, Any]] = []
    def add(source_id: str, label: str, source_type: str, url: str, purpose: str, status: str, priority: int, notes: str = "", allowed: bool = True):
        routes.append({
            "source_id": source_id,
            "label": label,
            "source_type": source_type,
            "url": url,
            "purpose": purpose,
            "status": status,
            "priority": priority,
            "allowed": allowed,
            "notes": notes,
            "anchors": anchors,
            "blocked_paths": [
                "No hacked/misconfigured/open IP cameras",
                "No Shodan/Censys/Insecam-style discovery",
                "No residential/workplace/private CCTV",
                "No face recognition or biometric matching",
                "No tracking a person across cameras",
                "No contacting camera owners/operators",
                "No tip submission from camera-source leads alone",
            ],
        })
    add("official-dot-traffic", "Official DOT/traffic camera maps", "official_traffic_camera", "route://official-dot-traffic", "Find public official traffic camera portals for case-relevant locations", "ready_requires_location_anchor", 92, "Use only official DOT/city traffic camera pages.")
    add("official-airport-port", "Official airport/port webcams", "official_airport_port_webcam", "route://official-airport-port", "Find official airport/port webcams for public transit/location context", "ready_requires_location_anchor", 80)
    add("official-city-webcams", "Official municipal webcams", "official_municipal_webcam", "route://official-city-webcams", "Find city/county public webcam pages", "ready_requires_location_anchor", 78)
    add("public-youtube-livecams", "Public YouTube live cameras", "public_media_livecam", "route://youtube-live-public-cams", "Search public livestreams already intentionally published", "ready_public_only", 65, "Do not use face matching or live tracking.")
    add("public-webcam-directories", "Public webcam directories", "public_webcam_directory", "route://public-webcam-directories", "Search public webcam directories for location context", "ready_public_only", 55, "Use only pages intentionally publishing public views.")
    add("open-ip-camera-search", "Open IP camera search", "open_ip_camera", "blocked://open-ip-camera-search", "Misconfigured exposed cameras", "blocked_prohibited", 0, "Blocked: open/misconfigured cameras are not consent-based public sources.", allowed=False)
    add("shodan-censys-insecam", "Shodan/Censys/Insecam camera discovery", "shodan_censys_insecam", "blocked://device-search", "Device discovery for exposed cameras", "blocked_prohibited", 0, "Blocked: do not discover or exploit exposed camera devices.", allowed=False)
    add("face-recognition", "Face recognition over public camera feeds", "face_recognition", "blocked://face-recognition", "Biometric identification/tracking", "blocked_prohibited", 0, "Blocked: no biometric matching or live tracking.", allowed=False)
    routes.sort(key=lambda r: r["priority"], reverse=True)
    return routes


def public_camera_queries(case: dict[str, Any], routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = case_camera_terms(case)
    name = terms["name"]
    aliases = terms["aliases"]
    anchors = terms["anchors"] or []
    queries: list[dict[str, Any]] = []
    def add(query: str, purpose: str, route_id: str, risk: str = "low", allowed: bool = True):
        queries.append({"query": query, "purpose": purpose, "route_id": route_id, "risk": risk, "allowed": allowed})
    # Case-specific snippets: safe, non-invasive public web search only.
    if name:
        add(f'"{name}" "camera" "Secret Service"', "Check public reporting mentioning cameras/security footage", "public-media-context")
        add(f'"{name}" "surveillance camera"', "Check public reporting for surveillance-camera mentions", "public-media-context")
        add(f'"{name}" "airport" "camera"', "Check public reporting for travel/camera context", "public-media-context")
    for alias in aliases[:4]:
        add(f'"{alias}" "webcam"', "Alias + public webcam context", "public-media-context", risk="medium")
        add(f'"{alias}" "YouTube" "live"', "Alias + public livestream context", "public-youtube-livecams", risk="medium")
    for anchor in anchors[:5]:
        add(f'{anchor} official traffic cameras', "Find official traffic camera portal for location anchor", "official-dot-traffic")
        add(f'{anchor} official public webcams', "Find official municipal/public webcams for location anchor", "official-city-webcams")
        add(f'{anchor} airport official webcam', "Find official airport webcam for location anchor", "official-airport-port")
    # Explicit no-go routes retained in report but never executed.
    add('site:insecam.org camera', "Blocked: exposed camera directory", "shodan-censys-insecam", risk="prohibited", allowed=False)
    add('intitle:"webcamXP" "admin" camera', "Blocked: misconfigured private cameras", "open-ip-camera-search", risk="prohibited", allowed=False)
    add(f'"{name}" face recognition public cameras', "Blocked: biometric identification/tracking", "face-recognition", risk="prohibited", allowed=False)
    return queries


def camera_result_score(case: dict[str, Any], result: dict[str, str]) -> dict[str, Any]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    haystack = f"{result.get('title','')} {result.get('snippet','')} {result.get('url','')}"
    score = 0
    reasons: list[str] = []
    if name and re.search(re.escape(name), haystack, re.I):
        score += 35; reasons.append("primary name match")
    if re.search(r"camera|webcam|livecam|traffic cam|surveillance|CCTV", haystack, re.I):
        score += 20; reasons.append("camera terms")
    if re.search(r"official|department of transportation|DOT|city of|airport|port authority|uscourts|justice.gov|state.gov", haystack, re.I):
        score += 20; reasons.append("official/public institution terms")
    domain = source_domain(result.get("url", ""))
    if domain.endswith(".gov") or domain.endswith(".us") or domain in {"youtube.com", "www.youtube.com"}:
        score += 15; reasons.append("public/official-ish domain")
    if re.search(r"insecam|shodan|censys|default password|admin", haystack, re.I):
        score = 0; reasons.append("blocked exposed-device signal")
    return {"score": min(score, 100), "reasons": reasons}


def cmd_camera_router(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    routes = public_camera_routes(case)
    queries = public_camera_queries(case, routes)
    outdir = OUTPUTS / case_id / "camera-router"
    outdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "routes": routes,
        "queries": queries,
        "ready_count": sum(1 for r in routes if r.get("allowed")),
        "blocked_count": sum(1 for r in routes if not r.get("allowed")),
        "allowed_queries": sum(1 for q in queries if q.get("allowed")),
        "blocked_queries": sum(1 for q in queries if not q.get("allowed")),
        "external_actions_performed": False,
        "policy": "Public/official camera-source routing only. No open IP cams, private CCTV, face recognition, contact, or tracking.",
    }
    write_json(outdir / "camera-router.json", payload)
    lines = [
        f"# Public Camera Source Router — {case_id}", "",
        f"- Generated: {payload['generated_at']}",
        f"- Ready routes: {payload['ready_count']}",
        f"- Blocked routes: {payload['blocked_count']}",
        f"- Allowed queries: {payload['allowed_queries']}",
        f"- Blocked queries: {payload['blocked_queries']}",
        "- External actions performed: false", "",
        "## Routes", "",
    ]
    for r in routes:
        mark = "READY" if r.get("allowed") else "BLOCKED"
        lines += [f"### {r['priority']} — {mark} — {r['label']}", f"- Type: `{r['source_type']}`", f"- Status: {r['status']}", f"- Purpose: {r['purpose']}", f"- Notes: {r.get('notes') or 'none'}", ""]
    lines += ["## Queries", ""]
    for q in queries:
        mark = "ALLOW" if q.get("allowed") else "BLOCK"
        lines += [f"- {mark}: `{q['query']}` — {q['purpose']}"]
    (outdir / "camera-router.md").write_text("\n".join(lines) + "\n")
    case.setdefault("tools", {})["camera_router"] = str((outdir / "camera-router.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({"case_id": case_id, "ready_routes": payload["ready_count"], "blocked_routes": payload["blocked_count"], "allowed_queries": payload["allowed_queries"], "blocked_queries": payload["blocked_queries"], "outdir": str(outdir), "external_actions_performed": False}, indent=2, ensure_ascii=False))


def cmd_camera_search(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    router_path = Path(args.router) if args.router else OUTPUTS / case_id / "camera-router" / "camera-router.json"
    if not router_path.exists():
        cmd_camera_router(argparse.Namespace(case=args.case))
    router = read_json(router_path)
    queries = [q for q in router.get("queries", []) if q.get("allowed")]
    if args.max_queries:
        queries = queries[: args.max_queries]
    outdir = OUTPUTS / case_id / "camera-search"
    outdir.mkdir(parents=True, exist_ok=True)
    evidence_dir = EVIDENCE / case_id / "camera-search"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ledger = evidence_dir / "camera-search-ledger.jsonl"
    rows: list[dict[str, Any]] = []
    for q in queries:
        results = ddg_search(q["query"], limit=args.per_query)
        if not results:
            row = {"case_id": case_id, "kind": "camera_search_no_results", **q, "captured_at": now_iso(), "external_actions_performed": False}
            append_jsonl(ledger, row); rows.append(row)
        for rank, result in enumerate(results, 1):
            if result.get("title") == "SEARCH_ERROR":
                row = {"case_id": case_id, "kind": "camera_search_error", **q, "error": result.get("snippet"), "captured_at": now_iso(), "external_actions_performed": False}
                append_jsonl(ledger, row); rows.append(row); continue
            scored = camera_result_score(case, result)
            row = {
                "case_id": case_id,
                "kind": "public_camera_search_result",
                **q,
                "rank": rank,
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "domain": source_domain(result.get("url", "")),
                "snippet": redact_sensitive_lines(result.get("snippet", "")),
                "camera_relevance_score": scored["score"],
                "camera_relevance_reasons": scored["reasons"],
                "captured_at": now_iso(),
                "external_actions_performed": False,
                "policy": "Search snippets/URLs only. No live camera viewing, no private/open IP cams, no face recognition, no contact.",
            }
            append_jsonl(ledger, row); rows.append(row)
        time.sleep(args.delay)
    result_rows = [r for r in rows if r.get("kind") == "public_camera_search_result"]
    result_rows.sort(key=lambda r: r.get("camera_relevance_score", 0), reverse=True)
    strong = [r for r in result_rows if r.get("camera_relevance_score", 0) >= args.threshold]
    status = "PUBLIC_CAMERA_LEADS_FOUND_REVIEW_REQUIRED" if strong else ("NO_STRONG_PUBLIC_CAMERA_LEADS" if result_rows else "NO_PUBLIC_CAMERA_RESULTS")
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "status": status,
        "queries_run": len(queries),
        "result_count": len(result_rows),
        "strong_count": len(strong),
        "top_results": result_rows[: args.limit],
        "ledger": str(ledger.relative_to(ROOT)),
        "external_actions_performed": False,
        "policy": "Public/official camera-source search only. Results are source leads, not identity evidence.",
    }
    write_json(outdir / "camera-search.json", payload)
    lines = [
        f"# Public Camera Search — {case_id}", "",
        f"- Generated: {payload['generated_at']}",
        f"- Status: {status}",
        f"- Queries run: {len(queries)}",
        f"- Results: {len(result_rows)}",
        f"- Strong leads: {len(strong)}",
        "- External actions performed: false", "",
        "## Top results", "",
    ]
    for r in payload["top_results"]:
        lines += [f"### {r.get('camera_relevance_score')} — {r.get('title') or r.get('url')}", f"- URL: {r.get('url')}", f"- Query: `{r.get('query')}`", f"- Reasons: {', '.join(r.get('camera_relevance_reasons') or [])}", f"- Snippet: {r.get('snippet')}", ""]
    lines += ["## Policy", "", "- No live camera viewing.", "- No open IP/misconfigured cameras.", "- No face recognition/tracking.", "- No contact with camera owners/operators.", "- No tip submission from camera-source leads alone."]
    (outdir / "camera-search.md").write_text("\n".join(lines) + "\n")
    case.setdefault("tools", {})["camera_search"] = str((outdir / "camera-search.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({"case_id": case_id, "status": status, "queries_run": len(queries), "result_count": len(result_rows), "strong_count": len(strong), "outdir": str(outdir), "external_actions_performed": False}, indent=2, ensure_ascii=False))


def route_runner_load_routes(case: dict[str, Any], include_camera: bool = True) -> list[dict[str, Any]]:
    case_id = case["case_id"]
    routes: list[dict[str, Any]] = []
    source_path = OUTPUTS / case_id / "source-router" / "public-records-source-router.json"
    if source_path.exists():
        for r in read_json(source_path).get("routes", []):
            if r.get("allowed") and r.get("status") == "ready":
                routes.append({**r, "router": "source-router", "route_kind": "public_record"})
    if include_camera:
        camera_path = OUTPUTS / case_id / "camera-router" / "camera-router.json"
        if camera_path.exists():
            for r in read_json(camera_path).get("routes", []):
                if r.get("allowed") and str(r.get("status", "")).startswith("ready"):
                    routes.append({**r, "router": "camera-router", "route_kind": "public_camera"})
    routes.sort(key=lambda r: r.get("priority", 0), reverse=True)
    return routes


def route_runner_materialize_url(route: dict[str, Any], case: dict[str, Any]) -> tuple[str, str]:
    """Return (url, materialization_note). route:// entries become safe search URLs, not device/protected access."""
    url = route.get("url", "")
    if url.startswith("http://") or url.startswith("https://"):
        return url, "direct_public_url"
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    anchors = route.get("anchors") or case_camera_terms(case).get("anchors") or []
    anchor = anchors[0] if anchors else name
    label = route.get("label", "public source")
    if url.startswith("route://"):
        query = f'{anchor} {label} official public'
        return "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query), "route_pointer_materialized_as_public_search"
    return "", "unsupported_or_blocked_route_url"


def route_runner_previous_hashes(ledger: Path) -> dict[str, str]:
    rows = read_jsonl(ledger) if ledger.exists() else []
    latest: dict[str, str] = {}
    for r in rows:
        rid = r.get("route_id") or r.get("source_id")
        h = r.get("excerpt_sha256") or r.get("response_sha256")
        if rid and h:
            latest[rid] = h
    return latest


def route_runner_score(route: dict[str, Any], fetch: dict[str, Any]) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    excerpt = str(fetch.get("excerpt") or fetch.get("reason") or "")
    if fetch.get("fetched"):
        score += 25; reasons.append("public fetch succeeded")
    status = fetch.get("http_status")
    if isinstance(status, int) and 200 <= status < 300:
        score += 20; reasons.append("2xx HTTP status")
    elif isinstance(status, int) and status in {401, 403, 429}:
        score -= 10; reasons.append(f"blocked/rate-limited status {status}")
    if route.get("route_kind") == "public_record":
        score += 20; reasons.append("public record route")
    if route.get("route_kind") == "public_camera":
        score += 5; reasons.append("camera route: source lead only")
    if route.get("official_domain") or source_domain(route.get("url", "")).endswith(".gov"):
        score += 20; reasons.append("official/government source")
    if fetch.get("changed_since_previous"):
        score += 20; reasons.append("content hash changed")
    if fetch.get("first_seen_route"):
        reasons.append("first route capture baseline")
    if fetch.get("materialization_note") == "route_pointer_materialized_as_public_search":
        score -= 5; reasons.append("route pointer materialized as search")
    if re.search(r"Technical Difficulties|Exception:\s*forbidden|HTTP Error 403|Please click here if you are not redirected|DuckDuckGo All Regions", excerpt, re.I):
        score -= 35; reasons.append("fetch returned blocking/search shell, not useful content")
    score = max(0, min(100, score))
    if score >= 75:
        tier = "A_REVIEW_NOW"
    elif score >= 45:
        tier = "B_KEEP_MONITORING"
    else:
        tier = "C_LOW_SIGNAL"
    return {"route_score": score, "route_tier": tier, "route_score_reasons": reasons}


def cmd_route_runner(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    if args.ensure_routers:
        if not (OUTPUTS / case_id / "source-router" / "public-records-source-router.json").exists():
            cmd_source_router(argparse.Namespace(case=args.case, ledger="", ready_only=False, limit=0, probe=False, probe_limit=0, delay=0.0))
        if args.include_camera and not (OUTPUTS / case_id / "camera-router" / "camera-router.json").exists():
            cmd_camera_router(argparse.Namespace(case=args.case))
    routes = route_runner_load_routes(case, include_camera=args.include_camera)
    if args.kind != "all":
        routes = [r for r in routes if r.get("route_kind") == args.kind]
    if args.limit:
        routes = routes[: args.limit]
    outdir = OUTPUTS / case_id / "route-runner"
    outdir.mkdir(parents=True, exist_ok=True)
    evidence_dir = EVIDENCE / case_id / "route-runner"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ledger = evidence_dir / "route-runner-ledger.jsonl"
    prev_hashes = route_runner_previous_hashes(ledger)
    rows: list[dict[str, Any]] = []
    for route in routes:
        route_id = route.get("source_id") or slugify(route.get("label", "route"))
        url, note = route_runner_materialize_url(route, case)
        if not url:
            fetch = {"fetched": False, "reason": note, "materialization_note": note, "external_actions_performed": False}
        elif args.dry_run:
            fetch = {"fetched": False, "reason": "dry_run", "materialized_url": url, "materialization_note": note, "external_actions_performed": False}
        else:
            fetch = safe_fetch_excerpt(url, max_chars=args.excerpt_chars)
            fetch["materialized_url"] = url
            fetch["materialization_note"] = note
        h = fetch.get("excerpt_sha256")
        fetch["changed_since_previous"] = bool(h and prev_hashes.get(route_id) and prev_hashes.get(route_id) != h)
        fetch["first_seen_route"] = bool(h and route_id not in prev_hashes)
        score = route_runner_score(route, fetch)
        row = {
            "case_id": case_id,
            "kind": "route_runner_capture",
            "route_id": route_id,
            "route_kind": route.get("route_kind"),
            "router": route.get("router"),
            "label": route.get("label"),
            "source_type": route.get("source_type") or route.get("access"),
            "original_url": route.get("url"),
            "captured_at": now_iso(),
            "external_actions_performed": False,
            "policy": "Public ready routes only. No private/paid/sealed/open-IP-camera access; no contact/submission.",
            **fetch,
            **score,
        }
        append_jsonl(ledger, row)
        rows.append(row)
        time.sleep(args.delay)
    changed = [r for r in rows if r.get("changed_since_previous")]
    review = [r for r in rows if r.get("route_tier") == "A_REVIEW_NOW"]
    status = "ROUTE_CHANGES_FOUND_REVIEW_REQUIRED" if changed else ("ROUTES_CAPTURED_REVIEW_AVAILABLE" if rows else "NO_READY_ROUTES")
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "status": status,
        "routes_run": len(rows),
        "changed_count": len(changed),
        "review_count": len(review),
        "captures": rows,
        "ledger": str(ledger.relative_to(ROOT)),
        "external_actions_performed": False,
        "policy": "Only ready public routes are run. No private/paid/sealed/open-camera-device access; no contact or submissions.",
    }
    write_json(outdir / "route-runner.json", payload)
    lines = [
        f"# Route Runner — {case_id}", "",
        f"- Generated: {payload['generated_at']}",
        f"- Status: {status}",
        f"- Routes run: {len(rows)}",
        f"- Changed: {len(changed)}",
        f"- A-review routes: {len(review)}",
        "- External actions performed: false", "",
        "## Captures", "",
    ]
    for r in rows[: args.report_limit]:
        lines += [
            f"### {r.get('route_score')} — {r.get('route_tier')} — {r.get('label')}",
            f"- Route: `{r.get('route_id')}` / `{r.get('route_kind')}`",
            f"- URL: {r.get('materialized_url') or r.get('original_url')}",
            f"- Fetched: {r.get('fetched')} / HTTP: {r.get('http_status', 'n/a')}",
            f"- First seen: {r.get('first_seen_route')} / Changed: {r.get('changed_since_previous')}",
            f"- Reasons: {', '.join(r.get('route_score_reasons') or [])}",
            f"- Excerpt preview: {str(r.get('excerpt', r.get('reason', '')))[:500]}", "",
        ]
    lines += ["## Policy", "", "- No private or paid sources.", "- No sealed filings.", "- No open IP/misconfigured camera discovery.", "- No face recognition/tracking.", "- No contact.", "- No tip submission."]
    (outdir / "route-runner.md").write_text("\n".join(lines) + "\n")
    case.setdefault("tools", {})["route_runner"] = str((outdir / "route-runner.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({"case_id": case_id, "status": status, "routes_run": len(rows), "changed_count": len(changed), "review_count": len(review), "outdir": str(outdir), "external_actions_performed": False}, indent=2, ensure_ascii=False))


def route_review_signal(case: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    aliases = entity.get("aliases") or []
    text = " ".join(str(row.get(k, "")) for k in ["label", "original_url", "materialized_url", "excerpt", "reason"])
    hits: dict[str, list[str]] = {
        "primary_name": [],
        "aliases": [],
        "reward_status": [],
        "court_docket": [],
        "case_status": [],
        "financial_crime": [],
        "law_enforcement": [],
        "camera_context": [],
        "blocking_shell": [],
    }
    if name and re.search(re.escape(name), text, re.I):
        hits["primary_name"].append(name)
    for alias in aliases:
        if alias and len(alias) > 2 and re.search(re.escape(alias), text, re.I):
            hits["aliases"].append(alias)
    patterns = {
        "reward_status": [r"reward", r"wanted", r"fugitive", r"tip", r"MostWanted", r"USSSMostWanted"],
        "court_docket": [r"case\s+no", r"docket", r"United States v", r"plea", r"sentenc", r"indict", r"forfeiture", r"Central District of California", r"CDCA"],
        "case_status": [r"arrested", r"captured", r"abscond", r"ankle", r"monitor", r"sentenced", r"in absentia", r"extradit"],
        "financial_crime": [r"money laundering", r"cryptocurrency", r"crypto", r"wire transfer", r"shell compan", r"victim funds", r"scam center", r"pig butchering"],
        "law_enforcement": [r"Secret Service", r"USSS", r"Justice Department", r"Department of State", r"U\.S\. Marshals", r"Homeland Security", r"HSI"],
        "camera_context": [r"camera", r"webcam", r"CCTV", r"traffic cam", r"livecam", r"surveillance"],
        "blocking_shell": [r"Technical Difficulties", r"Exception:\s*forbidden", r"HTTP Error 403", r"DuckDuckGo All Regions", r"Please click here if you are not redirected"],
    }
    for bucket, pats in patterns.items():
        for pat in pats:
            if re.search(pat, text, re.I):
                hits[bucket].append(pat)
    score = 0
    reasons: list[str] = []
    if hits["primary_name"]:
        score += 30; reasons.append("primary name present")
    if hits["aliases"]:
        score += min(20, 8 * len(set(hits["aliases"]))); reasons.append("alias present")
    if hits["reward_status"]:
        score += 15; reasons.append("reward/wanted/tip status terms")
    if hits["court_docket"]:
        score += 25; reasons.append("court/docket terms")
    if hits["case_status"]:
        score += 20; reasons.append("case status terms")
    if hits["financial_crime"]:
        score += 15; reasons.append("financial-crime terms")
    if hits["law_enforcement"]:
        score += 10; reasons.append("law-enforcement terms")
    if hits["camera_context"] and row.get("route_kind") == "public_camera":
        score += 3; reasons.append("camera source context only")
    if hits["blocking_shell"]:
        score -= 35; reasons.append("blocking/search shell, not substantive content")
    if row.get("changed_since_previous"):
        score += 20; reasons.append("route hash changed")
    if row.get("route_kind") == "public_camera" and not hits["primary_name"]:
        score -= 15; reasons.append("camera route without case identity signal")
    score = max(0, min(100, score))
    if score >= 75:
        verdict = "ACTIONABLE_REVIEW_SIGNAL"
    elif score >= 45:
        verdict = "MONITOR_SIGNAL"
    else:
        verdict = "PARK_LOW_SIGNAL"
    return {"review_score": score, "review_verdict": verdict, "review_reasons": reasons, "hits": {k: sorted(set(v)) for k, v in hits.items() if v}}


def cmd_review_extractor(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    route_path = Path(args.route_run) if args.route_run else OUTPUTS / case_id / "route-runner" / "route-runner.json"
    if not route_path.exists():
        raise SystemExit(f"Route runner output not found: {route_path}. Run route-runner first.")
    route_run = read_json(route_path)
    captures = route_run.get("captures", [])
    if args.min_route_score:
        captures = [r for r in captures if int(r.get("route_score") or 0) >= args.min_route_score]
    if args.tiers:
        wanted = {t.strip() for t in args.tiers.split(",") if t.strip()}
        captures = [r for r in captures if r.get("route_tier") in wanted]
    extracted: list[dict[str, Any]] = []
    for row in captures:
        sig = route_review_signal(case, row)
        extracted.append({
            "route_id": row.get("route_id"),
            "route_kind": row.get("route_kind"),
            "route_tier": row.get("route_tier"),
            "route_score": row.get("route_score"),
            "label": row.get("label"),
            "url": row.get("materialized_url") or row.get("original_url"),
            "fetched": row.get("fetched"),
            "http_status": row.get("http_status"),
            "changed_since_previous": row.get("changed_since_previous"),
            "excerpt_sha256": row.get("excerpt_sha256"),
            "excerpt_preview": str(row.get("excerpt") or row.get("reason") or "")[: args.preview_chars],
            **sig,
        })
    extracted.sort(key=lambda r: (r.get("review_score", 0), r.get("route_score", 0)), reverse=True)
    actionable = [r for r in extracted if r.get("review_verdict") == "ACTIONABLE_REVIEW_SIGNAL"]
    monitor = [r for r in extracted if r.get("review_verdict") == "MONITOR_SIGNAL"]
    if actionable:
        status = "ACTIONABLE_REVIEW_SIGNALS_FOUND"
    elif monitor:
        status = "MONITOR_SIGNALS_FOUND"
    else:
        status = "NO_ACTIONABLE_REVIEW_SIGNALS"
    outdir = OUTPUTS / case_id / "review-extractor"
    outdir.mkdir(parents=True, exist_ok=True)
    evidence_dir = EVIDENCE / case_id / "review-extractor"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ledger = evidence_dir / "review-extractor-ledger.jsonl"
    for row in extracted:
        append_jsonl(ledger, {"case_id": case_id, "kind": "route_review_extraction", "captured_at": now_iso(), "external_actions_performed": False, **row})
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "status": status,
        "input_route_run": str(route_path.relative_to(ROOT)) if route_path.is_relative_to(ROOT) else str(route_path),
        "reviewed_count": len(extracted),
        "actionable_count": len(actionable),
        "monitor_count": len(monitor),
        "top_signals": extracted[: args.limit],
        "ledger": str(ledger.relative_to(ROOT)),
        "refresh_recommended": bool(actionable),
        "external_actions_performed": False,
        "policy": "Review extraction only. No external contact, no private sources, no submissions.",
    }
    write_json(outdir / "review-extractor.json", payload)
    lines = [
        f"# Review Extractor — {case_id}", "",
        f"- Generated: {payload['generated_at']}",
        f"- Status: {status}",
        f"- Reviewed routes: {len(extracted)}",
        f"- Actionable: {len(actionable)}",
        f"- Monitor: {len(monitor)}",
        f"- Refresh recommended: {payload['refresh_recommended']}",
        "- External actions performed: false", "",
        "## Top signals", "",
    ]
    for r in payload["top_signals"]:
        lines += [
            f"### {r.get('review_score')} — {r.get('review_verdict')} — {r.get('label')}",
            f"- Route: `{r.get('route_id')}` / `{r.get('route_kind')}` / route tier `{r.get('route_tier')}`",
            f"- URL: {r.get('url')}",
            f"- Changed: {r.get('changed_since_previous')} / HTTP: {r.get('http_status', 'n/a')}",
            f"- Reasons: {', '.join(r.get('review_reasons') or []) or 'none'}",
            f"- Hits: `{json.dumps(r.get('hits') or {}, ensure_ascii=False)[:600]}`",
            f"- Preview: {r.get('excerpt_preview')}", "",
        ]
    lines += ["## Decision", ""]
    if actionable:
        lines.append("- Actionable signals found. Refresh graph/hypotheses and draft review note before any external action.")
    elif monitor:
        lines.append("- Monitor-only signals found. Keep route runner active; no tip/update yet.")
    else:
        lines.append("- No actionable review signal. Keep as baseline/monitoring evidence.")
    lines += ["", "## Policy", "", "- No contact.", "- No private/paid sources.", "- No tip submission."]
    (outdir / "review-extractor.md").write_text("\n".join(lines) + "\n")
    case.setdefault("tools", {})["review_extractor"] = str((outdir / "review-extractor.json").relative_to(ROOT))
    save_case(case)
    if args.refresh and actionable:
        # Re-run graph/hypotheses on canonical evidence; review extractor itself remains non-mutating beyond case tool pointer.
        cmd_graph_score(argparse.Namespace(case=args.case, ledger=""))
        cmd_hypotheses(argparse.Namespace(case=args.case, ledger="", score="", limit=0))
    print(json.dumps({"case_id": case_id, "status": status, "reviewed_count": len(extracted), "actionable_count": len(actionable), "monitor_count": len(monitor), "refresh_recommended": bool(actionable), "outdir": str(outdir), "external_actions_performed": False}, indent=2, ensure_ascii=False))


BEYOND_OFFICIAL_BLOCKED = [
    "No leaked/private databases or breach dumps",
    "No personal address/phone/relative searches",
    "No contacting victims, witnesses, suspects, relatives, associates, companies, exchanges, or reporters",
    "No paid/private investigator databases",
    "No credentialed blockchain analytics accounts unless separately authorized",
    "No hacked infrastructure or dark-web access",
    "No public accusation or tip submission from uncorroborated leads",
]


def beyond_official_routes(case: dict[str, Any]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    def add(source_id: str, label: str, source_type: str, purpose: str, priority: int, status: str = "ready", notes: str = "", allowed: bool = True):
        routes.append({
            "source_id": source_id,
            "label": label,
            "source_type": source_type,
            "purpose": purpose,
            "priority": priority,
            "status": status,
            "allowed": allowed,
            "notes": notes,
            "blocked_paths": BEYOND_OFFICIAL_BLOCKED,
        })
    add("crypto-exchange-compliance", "Crypto exchange / compliance public posts", "crypto_compliance_public", "Find exchange/compliance writeups mentioning case, wallets, scam typology, or recovery actions", 95)
    add("blockchain-public-intel", "Public blockchain intelligence/blogs", "blockchain_public_intel", "Find public wallet, flow, typology, seizure, or laundering-route references", 92)
    add("scam-victim-public-reports", "Public scam/victim report aggregators", "victim_report_public", "Find public reports by scam type, entity names, domains, aliases, or wallet fragments", 86, notes="Only public posts; do not contact victims.")
    add("domain-infrastructure-public", "Domain/infrastructure public OSINT", "domain_public_osint", "Find spoofed trading domains, hosting clues, public RDAP/WHOIS, archived pages", 82)
    add("corporate-registry-public", "Public corporate registry / shell-company mentions", "corporate_registry_public", "Find publicly named shell companies/entities from reporting or filings", 78)
    add("international-media", "International/local media", "media_public", "Find non-US public reporting, Cambodia/China/St. Kitts/crypto scam center context", 75)
    add("sanctions-watchlists", "Sanctions/watchlist/public risk databases", "watchlist_public", "Check public sanctions/adverse-media style references", 70)
    add("academic-ngo-reports", "Academic/NGO scam-center reports", "ngo_academic_public", "Understand scam-center geography/operators/typologies for hypothesis generation", 62)
    add("social-snippet-public", "Public social/web snippet crosscheck", "social_snippet_public", "Search public snippets only for distinctive aliases connected to case terms", 55, notes="No profile opening/contact; weak correlation only.")
    add("dark-web-leaks", "Dark web / leaked databases", "leaked_private_data", "Leaked/private data route", 0, "blocked_prohibited", "Blocked: no leaked/private/dark-web data.", allowed=False)
    add("people-search-doxxing", "People-search / relatives / addresses", "doxxing_private", "Personal data route", 0, "blocked_prohibited", "Blocked: no doxxing/private personal data.", allowed=False)
    routes.sort(key=lambda r: r["priority"], reverse=True)
    return routes


def beyond_official_queries(case: dict[str, Any]) -> list[dict[str, Any]]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    aliases = [a for a in (entity.get("aliases") or []) if a and len(a) > 2]
    queries: list[dict[str, Any]] = []
    def add(q: str, purpose: str, route_id: str, risk: str = "low", allowed: bool = True):
        queries.append({"query": q, "purpose": purpose, "route_id": route_id, "risk": risk, "allowed": allowed})
    if name:
        add(f'"{name}" cryptocurrency scam wallet', "Wallet/crypto public references", "blockchain-public-intel")
        add(f'"{name}" "Binance" OR "Tether" OR "TRON" OR "USDT"', "Exchange/chain context", "crypto-exchange-compliance")
        add(f'"{name}" "pig butchering" "Cambodia"', "Scam-center context", "international-media")
        add(f'"{name}" "scam center" OR "fraud compound"', "Scam-center/operator context", "academic-ngo-reports")
        add(f'"{name}" "shell company" OR "bank account"', "Shell-company public mentions", "corporate-registry-public")
        add(f'"{name}" "spoofed" "domain" cryptocurrency', "Spoofed platform/domain artifacts", "domain-infrastructure-public")
        add(f'"{name}" "victim" "cryptocurrency"', "Public victim/report references", "scam-victim-public-reports")
        add(f'"{name}" "St. Kitts" "Nevis"', "International identity/public reporting context", "international-media")
    for alias in aliases[:6]:
        if len(alias) <= 3:
            add(f'"{alias}" "{name}"', "Short/common alias requires primary-name anchor", "social-snippet-public", risk="medium")
            continue
        add(f'"{alias}" "Daren Li"', "Alias anchored to primary name", "social-snippet-public", risk="medium")
        add(f'"{alias}" "money laundering"', "Alias + allegation", "social-snippet-public", risk="medium")
        add(f'"{alias}" cryptocurrency scam', "Alias + scam typology", "social-snippet-public", risk="medium")
    # Entity/topic searches not person-private.
    add('"$73.6 million" "victim funds" cryptocurrency scam', "Amount-specific public reporting", "crypto-exchange-compliance")
    add('"59.8 million" "shell companies" "victim proceeds"', "Shell-company amount-specific reporting", "corporate-registry-public")
    add('"Cambodia" "cryptocurrency investment scam" "money laundering" "shell companies"', "Scam-center laundering ecosystem", "academic-ngo-reports")
    # blocked examples
    add(f'"{name}" address phone relatives', "Blocked doxxing query", "people-search-doxxing", risk="prohibited", allowed=False)
    add(f'"{name}" leaked database passport', "Blocked leaked/private data query", "dark-web-leaks", risk="prohibited", allowed=False)
    return queries


def beyond_result_score(case: dict[str, Any], result: dict[str, str], route_id: str) -> dict[str, Any]:
    entity = (case.get("entities") or [{}])[0]
    name = entity.get("name", "")
    aliases = entity.get("aliases") or []
    haystack = f"{result.get('title','')} {result.get('snippet','')} {result.get('url','')}"
    score = 0
    reasons: list[str] = []
    if name and re.search(re.escape(name), haystack, re.I):
        score += 30; reasons.append("primary name match")
    alias_hits = []
    for alias in aliases:
        if alias and len(alias) > 2 and re.search(re.escape(alias), haystack, re.I):
            alias_hits.append(alias)
    if alias_hits:
        score += min(15, 6 * len(set(alias_hits))); reasons.append("alias hits: " + ", ".join(sorted(set(alias_hits))))
    if re.search(r"wallet|address|transaction|blockchain|USDT|TRON|Bitcoin|Ethereum|stablecoin|seiz", haystack, re.I):
        score += 25; reasons.append("crypto-rail artifact terms")
    if re.search(r"domain|spoofed|website|hosting|registrar|WHOIS|RDAP", haystack, re.I):
        score += 20; reasons.append("infrastructure/domain terms")
    if re.search(r"shell compan|bank account|wire transfer|victim funds|proceeds", haystack, re.I):
        score += 20; reasons.append("shell/banking/funds terms")
    if re.search(r"Cambodia|scam center|fraud compound|pig butchering|human trafficking", haystack, re.I):
        score += 15; reasons.append("scam-center context")
    if re.search(r"Justice|Secret Service|State Department|DOJ|USSS", haystack, re.I):
        score += 8; reasons.append("official-case context referenced")
    domain = source_domain(result.get("url", ""))
    if domain in {"binance.com", "chainalysis.com", "trmlabs.com", "elliptic.co", "tronscan.org", "etherscan.io", "bitcoinabuse.com", "scamsearch.io"}:
        score += 12; reasons.append("higher-signal crypto/compliance domain")
    if route_id in {"dark-web-leaks", "people-search-doxxing"} or re.search(r"leaked|ssn|passport|address|phone|relative", haystack, re.I):
        score = 0; reasons.append("blocked private/doxxing/leak signal")
    score = max(0, min(100, score))
    if score >= 75:
        verdict = "A_CORROBORATE_NOW"
    elif score >= 45:
        verdict = "B_REVIEW"
    else:
        verdict = "C_PARK"
    return {"beyond_score": score, "beyond_verdict": verdict, "beyond_reasons": reasons, "alias_hits": sorted(set(alias_hits))}


def cmd_beyond_router(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    routes = beyond_official_routes(case)
    queries = beyond_official_queries(case)
    outdir = OUTPUTS / case_id / "beyond-official-router"
    outdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "routes": routes,
        "queries": queries,
        "ready_count": sum(1 for r in routes if r.get("allowed")),
        "blocked_count": sum(1 for r in routes if not r.get("allowed")),
        "allowed_queries": sum(1 for q in queries if q.get("allowed")),
        "blocked_queries": sum(1 for q in queries if not q.get("allowed")),
        "external_actions_performed": False,
        "policy": "Beyond-official public OSINT only. No leaks/private data/doxxing/contact/submission.",
    }
    write_json(outdir / "beyond-official-router.json", payload)
    lines = [f"# Beyond Official Source Router — {case_id}", "", f"- Generated: {payload['generated_at']}", f"- Ready routes: {payload['ready_count']}", f"- Blocked routes: {payload['blocked_count']}", f"- Allowed queries: {payload['allowed_queries']}", f"- Blocked queries: {payload['blocked_queries']}", "- External actions performed: false", "", "## Routes", ""]
    for r in routes:
        mark = "READY" if r.get("allowed") else "BLOCKED"
        lines += [f"### {r['priority']} — {mark} — {r['label']}", f"- Type: `{r['source_type']}`", f"- Purpose: {r['purpose']}", f"- Notes: {r.get('notes') or 'none'}", ""]
    lines += ["## Queries", ""]
    for q in queries:
        mark = "ALLOW" if q.get("allowed") else "BLOCK"
        lines.append(f"- {mark}: `{q['query']}` — {q['purpose']}")
    (outdir / "beyond-official-router.md").write_text("\n".join(lines) + "\n")
    case.setdefault("tools", {})["beyond_official_router"] = str((outdir / "beyond-official-router.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({"case_id": case_id, "ready_routes": payload["ready_count"], "blocked_routes": payload["blocked_count"], "allowed_queries": payload["allowed_queries"], "blocked_queries": payload["blocked_queries"], "outdir": str(outdir), "external_actions_performed": False}, indent=2, ensure_ascii=False))


def cmd_beyond_search(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    router_path = Path(args.router) if args.router else OUTPUTS / case_id / "beyond-official-router" / "beyond-official-router.json"
    if not router_path.exists():
        cmd_beyond_router(argparse.Namespace(case=args.case))
    router = read_json(router_path)
    queries = [q for q in router.get("queries", []) if q.get("allowed")]
    if args.route_id:
        wanted = set(args.route_id)
        queries = [q for q in queries if q.get("route_id") in wanted]
    if args.max_queries:
        queries = queries[: args.max_queries]
    outdir = OUTPUTS / case_id / "beyond-official-search"
    outdir.mkdir(parents=True, exist_ok=True)
    evidence_dir = EVIDENCE / case_id / "beyond-official-search"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ledger = evidence_dir / "beyond-official-search-ledger.jsonl"
    rows: list[dict[str, Any]] = []
    for q in queries:
        results = ddg_search(q["query"], limit=args.per_query)
        if not results:
            row = {"case_id": case_id, "kind": "beyond_official_no_results", **q, "captured_at": now_iso(), "external_actions_performed": False}
            append_jsonl(ledger, row); rows.append(row)
        for rank, result in enumerate(results, 1):
            if result.get("title") == "SEARCH_ERROR":
                row = {"case_id": case_id, "kind": "beyond_official_search_error", **q, "error": result.get("snippet"), "captured_at": now_iso(), "external_actions_performed": False}
                append_jsonl(ledger, row); rows.append(row); continue
            scored = beyond_result_score(case, result, q.get("route_id", ""))
            row = {
                "case_id": case_id,
                "kind": "beyond_official_public_result",
                **q,
                "rank": rank,
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "domain": source_domain(result.get("url", "")),
                "snippet": redact_sensitive_lines(result.get("snippet", "")),
                "captured_at": now_iso(),
                "external_actions_performed": False,
                "policy": "Public web snippets only. No private data, no contact, no submissions.",
                **scored,
            }
            append_jsonl(ledger, row); rows.append(row)
        time.sleep(args.delay)
    result_rows = [r for r in rows if r.get("kind") == "beyond_official_public_result"]
    result_rows.sort(key=lambda r: r.get("beyond_score", 0), reverse=True)
    a = [r for r in result_rows if r.get("beyond_verdict") == "A_CORROBORATE_NOW"]
    b = [r for r in result_rows if r.get("beyond_verdict") == "B_REVIEW"]
    status = "BEYOND_OFFICIAL_A_SIGNALS_FOUND" if a else ("BEYOND_OFFICIAL_B_SIGNALS_FOUND" if b else "NO_STRONG_BEYOND_OFFICIAL_SIGNALS")
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "status": status,
        "queries_run": len(queries),
        "result_count": len(result_rows),
        "a_count": len(a),
        "b_count": len(b),
        "top_results": result_rows[: args.limit],
        "ledger": str(ledger.relative_to(ROOT)),
        "external_actions_performed": False,
        "policy": "Beyond-official public OSINT only. Results require corroboration before action.",
    }
    write_json(outdir / "beyond-official-search.json", payload)
    lines = [f"# Beyond Official Search — {case_id}", "", f"- Generated: {payload['generated_at']}", f"- Status: {status}", f"- Queries run: {len(queries)}", f"- Results: {len(result_rows)}", f"- A signals: {len(a)}", f"- B signals: {len(b)}", "- External actions performed: false", "", "## Top results", ""]
    for r in payload["top_results"]:
        lines += [f"### {r.get('beyond_score')} — {r.get('beyond_verdict')} — {r.get('title') or r.get('url')}", f"- Route: `{r.get('route_id')}`", f"- URL: {r.get('url')}", f"- Query: `{r.get('query')}`", f"- Reasons: {', '.join(r.get('beyond_reasons') or []) or 'none'}", f"- Snippet: {r.get('snippet')}", ""]
    lines += ["## Policy", "", "- Public snippets only.", "- No private/leaked data.", "- No contact.", "- No tip submission."]
    (outdir / "beyond-official-search.md").write_text("\n".join(lines) + "\n")
    case.setdefault("tools", {})["beyond_official_search"] = str((outdir / "beyond-official-search.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({"case_id": case_id, "status": status, "queries_run": len(queries), "result_count": len(result_rows), "a_count": len(a), "b_count": len(b), "outdir": str(outdir), "external_actions_performed": False}, indent=2, ensure_ascii=False))


def beyond_artifacts_from_text(text: str) -> dict[str, Any]:
    artifacts: dict[str, Any] = {
        "aliases": [],
        "platforms": [],
        "companies": [],
        "accounts": [],
        "locations": [],
        "dates": [],
        "amounts": [],
        "crypto_terms": [],
        "investigative_hooks": [],
    }
    alias_patterns = [r"aliases? such as [“\"]([^”\"]+)[”\"] and [“\"]([^”\"]+)[”\"]", r"under aliases? such as ([A-Z0-9_\-]+) and ([A-Z0-9_\-]+)"]
    for pat in alias_patterns:
        for m in re.findall(pat, text, re.I):
            for item in (m if isinstance(m, tuple) else [m]):
                artifacts["aliases"].append(item.strip(" .,'\"“”"))
    for m in re.findall(r"including spoofed websites designed to mimic legitimate exchanges such as [“\"]([^”\"]+)[”\"]", text, re.I):
        artifacts["platforms"].append(m.strip(" .,’‘,\"“”"))
    cm = re.search(r"Entities such as (.+?) were used", text, re.I | re.S)
    if cm:
        segment = re.sub(r"\s+", " ", cm.group(1)).strip(" .")
        # Known pattern in TRM article: company name contains "and".
        if re.search(r"CMD Export and Import", segment, re.I):
            artifacts["companies"].append("CMD Export and Import")
        if re.search(r"Crestview Services", segment, re.I):
            artifacts["companies"].append("Crestview Services, Inc")
        if not artifacts["companies"]:
            for part in re.split(r",\s+and\s+", segment):
                part = part.strip(" .,’‘,\"“”")
                if part:
                    artifacts["companies"].append(part)
    for pat in [r"(Bahamas Account #[0-9]+)", r"([A-Za-z]+ Account #[0-9]+)"]:
        for m in re.findall(pat, text): artifacts["accounts"].append(m.strip())
    for loc in ["Hartsfield-Jackson Atlanta International Airport", "Cambodia", "Kingdom of Cambodia", "Bahamas", "Los Angeles", "Central District of California", "Dominican Republic", "St. Kitts and Nevis", "China"]:
        if re.search(re.escape(loc), text, re.I): artifacts["locations"].append(loc)
    for m in re.findall(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4}|\b\d{4}\b", text):
        artifacts["dates"].append(m.strip())
    for m in re.findall(r"USD\s*[0-9.]+\s*(?:million|billion)|\$\s*[0-9.]+\s*(?:million|billion)|[0-9.]+\s*million", text, re.I):
        artifacts["amounts"].append(m.strip())
    for term in ["USDT", "Tether", "TRON", "Bitcoin", "Ethereum", "virtual asset service provider", "VASP", "blockchain intelligence", "stablecoin"]:
        if re.search(re.escape(term), text, re.I): artifacts["crypto_terms"].append(term)
    for hook in ["74 shell companies", "Victim 1", "May and August 2022", "CoinZoom", "Bahamas Account #2", "Los Angeles-based co-conspirator", "iPhone seized from a co-conspirator", "frequent logins from Cambodia"]:
        if re.search(re.escape(hook), text, re.I): artifacts["investigative_hooks"].append(hook)
    return {k: sorted(set(v)) for k, v in artifacts.items() if v}


def beyond_artifact_queries(case: dict[str, Any], artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    name = (case.get("entities") or [{}])[0].get("name", "")
    queries: list[dict[str, Any]] = []
    def add(q: str, purpose: str, artifact_type: str, risk: str = "low"):
        queries.append({"query": q, "purpose": purpose, "artifact_type": artifact_type, "risk": risk, "allowed": True})
    for alias in artifacts.get("aliases", []):
        add(f'"{alias}" "{name}"', "New alias anchored to primary name", "alias", "medium")
        add(f'"{alias}" "money laundering" cryptocurrency', "Alias + allegation/crypto context", "alias", "medium")
    for platform in artifacts.get("platforms", []):
        add(f'"{platform}" "Daren Li"', "Spoofed platform linked to case", "platform")
        add(f'"{platform}" "pig butchering" "USDT"', "Spoofed platform scam context", "platform")
    for company in artifacts.get("companies", []):
        add(f'"{company}" "Daren Li"', "Shell company linked to primary name", "company")
        add(f'"{company}" "cryptocurrency" "wire transfer"', "Shell company financial context", "company")
    for account in artifacts.get("accounts", []):
        add(f'"{account}" "Daren Li"', "Named account reference", "account")
    for hook in artifacts.get("investigative_hooks", []):
        if hook in {"Victim 1", "iPhone seized from a co-conspirator"}:
            continue
        add(f'"{hook}" "Daren Li"', "Hook anchored to primary name", "hook")
    return queries


def cmd_beyond_extract(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    search_path = Path(args.search) if args.search else OUTPUTS / case_id / "beyond-official-search" / "beyond-official-search.json"
    if not search_path.exists():
        raise SystemExit(f"Beyond search output not found: {search_path}. Run beyond-search first.")
    search = read_json(search_path)
    results = search.get("top_results", [])[: args.max_results]
    outdir = OUTPUTS / case_id / "beyond-evidence-extractor"
    outdir.mkdir(parents=True, exist_ok=True)
    evidence_dir = EVIDENCE / case_id / "beyond-evidence-extractor"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ledger = evidence_dir / "beyond-evidence-extractor-ledger.jsonl"
    extracted: list[dict[str, Any]] = []
    all_queries: list[dict[str, Any]] = []
    for result in results:
        url = result.get("url", "")
        fetch = safe_fetch_excerpt(url, max_chars=args.excerpt_chars)
        text = fetch.get("excerpt", "") or ""
        artifacts = beyond_artifacts_from_text(text)
        queries = beyond_artifact_queries(case, artifacts)
        all_queries.extend(queries)
        row = {
            "case_id": case_id,
            "kind": "beyond_evidence_artifact_extraction",
            "source_title": result.get("title"),
            "url": url,
            "domain": source_domain(url),
            "fetched": fetch.get("fetched"),
            "http_status": fetch.get("http_status"),
            "excerpt_sha256": fetch.get("excerpt_sha256"),
            "artifacts": artifacts,
            "derived_query_count": len(queries),
            "captured_at": now_iso(),
            "external_actions_performed": False,
            "policy": "Public article extraction only. No contact, private data, leaks, or submissions.",
        }
        append_jsonl(ledger, row); extracted.append(row)
        time.sleep(args.delay)
    # De-dupe derived queries.
    seen = set(); deduped=[]
    for q in all_queries:
        if q["query"] in seen: continue
        seen.add(q["query"]); deduped.append(q)
    strength = 0
    artifact_counts: dict[str, int] = {}
    for row in extracted:
        for k, v in (row.get("artifacts") or {}).items():
            artifact_counts[k] = artifact_counts.get(k, 0) + len(v)
    if artifact_counts.get("aliases"): strength += 25
    if artifact_counts.get("companies"): strength += 25
    if artifact_counts.get("platforms"): strength += 20
    if artifact_counts.get("accounts"): strength += 20
    if artifact_counts.get("locations"): strength += 10
    status = "NEW_BEYOND_ARTIFACTS_FOUND" if strength >= 25 else "NO_USEFUL_BEYOND_ARTIFACTS"
    payload = {
        "case_id": case_id,
        "generated_at": now_iso(),
        "status": status,
        "artifact_strength_score": min(strength, 100),
        "artifact_counts": artifact_counts,
        "sources_reviewed": len(extracted),
        "extractions": extracted,
        "derived_queries": deduped,
        "ledger": str(ledger.relative_to(ROOT)),
        "external_actions_performed": False,
        "policy": "Beyond-official extraction is public-source only; derived queries require safe-search workers and corroboration.",
    }
    write_json(outdir / "beyond-evidence-extractor.json", payload)
    lines = [f"# Beyond Evidence Extractor — {case_id}", "", f"- Generated: {payload['generated_at']}", f"- Status: {status}", f"- Artifact strength: {payload['artifact_strength_score']}", f"- Sources reviewed: {len(extracted)}", f"- Derived queries: {len(deduped)}", "- External actions performed: false", "", "## Artifact counts", ""]
    for k, v in sorted(artifact_counts.items()): lines.append(f"- {k}: {v}")
    lines += ["", "## Extracted artifacts", ""]
    for row in extracted:
        lines += [f"### {row.get('source_title') or row.get('url')}", f"- URL: {row.get('url')}", f"- Fetched: {row.get('fetched')} / HTTP: {row.get('http_status')}", f"- Artifacts: `{json.dumps(row.get('artifacts') or {}, ensure_ascii=False)[:1200]}`", ""]
    lines += ["## Derived queries", ""]
    for q in deduped[: args.query_report_limit]: lines.append(f"- `{q['query']}` — {q['purpose']}")
    lines += ["", "## Policy", "", "- Public articles only.", "- No private/leaked data.", "- No contact.", "- No submission."]
    (outdir / "beyond-evidence-extractor.md").write_text("\n".join(lines) + "\n")
    case.setdefault("tools", {})["beyond_evidence_extractor"] = str((outdir / "beyond-evidence-extractor.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({"case_id": case_id, "status": status, "artifact_strength_score": min(strength, 100), "artifact_counts": artifact_counts, "sources_reviewed": len(extracted), "derived_queries": len(deduped), "outdir": str(outdir), "external_actions_performed": False}, indent=2, ensure_ascii=False))


def cmd_beyond_derived_search(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    case_id = case["case_id"]
    extract_path = Path(args.extract) if args.extract else OUTPUTS / case_id / "beyond-evidence-extractor" / "beyond-evidence-extractor.json"
    if not extract_path.exists():
        raise SystemExit(f"Beyond extractor output not found: {extract_path}. Run beyond-extract first.")
    extraction = read_json(extract_path)
    queries = [q for q in extraction.get("derived_queries", []) if q.get("allowed")]
    if args.artifact_type:
        wanted = set(args.artifact_type)
        queries = [q for q in queries if q.get("artifact_type") in wanted]
    if args.max_queries:
        queries = queries[: args.max_queries]
    outdir = OUTPUTS / case_id / "beyond-derived-search"
    outdir.mkdir(parents=True, exist_ok=True)
    evidence_dir = EVIDENCE / case_id / "beyond-derived-search"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ledger = evidence_dir / "beyond-derived-search-ledger.jsonl"
    rows: list[dict[str, Any]] = []
    for q in queries:
        results = ddg_search(q["query"], limit=args.per_query)
        if not results:
            row = {"case_id": case_id, "kind": "beyond_derived_no_results", **q, "captured_at": now_iso(), "external_actions_performed": False}
            append_jsonl(ledger, row); rows.append(row)
        for rank, result in enumerate(results, 1):
            if result.get("title") == "SEARCH_ERROR":
                row = {"case_id": case_id, "kind": "beyond_derived_search_error", **q, "error": result.get("snippet"), "captured_at": now_iso(), "external_actions_performed": False}
                append_jsonl(ledger, row); rows.append(row); continue
            scored = beyond_result_score(case, result, q.get("artifact_type", ""))
            # artifact-specific boost only when query phrase appears in title/snippet/url
            phrase = q.get("query", "").split('"')[1] if '"' in q.get("query", "") else ""
            haystack = f"{result.get('title','')} {result.get('snippet','')} {result.get('url','')}"
            if phrase and re.search(re.escape(phrase), haystack, re.I):
                scored["beyond_score"] = min(100, scored["beyond_score"] + 20)
                scored["beyond_reasons"].append("derived artifact phrase hit")
                scored["beyond_verdict"] = "A_CORROBORATE_NOW" if scored["beyond_score"] >= 75 else ("B_REVIEW" if scored["beyond_score"] >= 45 else "C_PARK")
            row = {"case_id": case_id, "kind": "beyond_derived_public_result", **q, "rank": rank, "title": result.get("title", ""), "url": result.get("url", ""), "domain": source_domain(result.get("url", "")), "snippet": redact_sensitive_lines(result.get("snippet", "")), "captured_at": now_iso(), "external_actions_performed": False, "policy": "Derived artifact public search only. No private data/contact/submission.", **scored}
            append_jsonl(ledger, row); rows.append(row)
        time.sleep(args.delay)
    result_rows = [r for r in rows if r.get("kind") == "beyond_derived_public_result"]
    result_rows.sort(key=lambda r: r.get("beyond_score", 0), reverse=True)
    a = [r for r in result_rows if r.get("beyond_verdict") == "A_CORROBORATE_NOW"]
    b = [r for r in result_rows if r.get("beyond_verdict") == "B_REVIEW"]
    status = "DERIVED_A_SIGNALS_FOUND" if a else ("DERIVED_B_SIGNALS_FOUND" if b else "NO_STRONG_DERIVED_SIGNALS")
    payload = {"case_id": case_id, "generated_at": now_iso(), "status": status, "queries_run": len(queries), "result_count": len(result_rows), "a_count": len(a), "b_count": len(b), "top_results": result_rows[: args.limit], "ledger": str(ledger.relative_to(ROOT)), "external_actions_performed": False, "policy": "Derived artifact search uses public snippets only; corroboration required."}
    write_json(outdir / "beyond-derived-search.json", payload)
    lines = [f"# Beyond Derived Search — {case_id}", "", f"- Generated: {payload['generated_at']}", f"- Status: {status}", f"- Queries run: {len(queries)}", f"- Results: {len(result_rows)}", f"- A signals: {len(a)}", f"- B signals: {len(b)}", "- External actions performed: false", "", "## Top results", ""]
    for r in payload["top_results"]:
        lines += [f"### {r.get('beyond_score')} — {r.get('beyond_verdict')} — {r.get('title') or r.get('url')}", f"- Artifact: `{r.get('artifact_type')}`", f"- URL: {r.get('url')}", f"- Query: `{r.get('query')}`", f"- Reasons: {', '.join(r.get('beyond_reasons') or []) or 'none'}", f"- Snippet: {r.get('snippet')}", ""]
    lines += ["## Policy", "", "- Public snippets only.", "- No private/leaked data.", "- No contact.", "- No submission."]
    (outdir / "beyond-derived-search.md").write_text("\n".join(lines) + "\n")
    case.setdefault("tools", {})["beyond_derived_search"] = str((outdir / "beyond-derived-search.json").relative_to(ROOT))
    save_case(case)
    print(json.dumps({"case_id": case_id, "status": status, "queries_run": len(queries), "result_count": len(result_rows), "a_count": len(a), "b_count": len(b), "outdir": str(outdir), "external_actions_performed": False}, indent=2, ensure_ascii=False))


def cmd_html_report(args: argparse.Namespace) -> None:
    script = ROOT / "scripts" / "html_report.py"
    cmd = [sys.executable, str(script), args.case]
    if args.output:
        cmd.extend(["--output", args.output])
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if proc.returncode:
        raise SystemExit(proc.returncode)

def cmd_intake_text(args: argparse.Namespace) -> None:
    text = args.text or Path(args.file).read_text()
    fields = extract_notice_fields(text)
    title_name = fields.get("name") or args.title or "reward notice"
    case_id = args.case_id or slugify(f"{title_name}-{fields.get('agency', 'notice')}")
    source = {
        "url": args.source_url or args.file or "manual-text",
        "agency": fields.get("agency") or "Unknown/needs verification",
        "captured_at": now_iso(),
        "input_type": "text",
    }
    case = build_case(case_id, args.title or title_name, source, fields, text=text)
    paths = write_case_bundle(case, Path(args.file) if args.file else None)
    print(json.dumps({"case_id": case_id, "paths": paths, "external_actions_performed": False}, indent=2, ensure_ascii=False))


def cmd_intake_image(args: argparse.Namespace) -> None:
    image = Path(args.image).expanduser().resolve()
    if not image.exists():
        raise SystemExit(f"Image not found: {image}")
    text = args.text or ""
    fields = extract_notice_fields(text) if text else {"name": args.title or image.stem, "aliases": [], "reward_amount_usd": None, "allegations": [], "official_channels": [], "agency": "Unknown/needs verification"}
    title_name = fields.get("name") or args.title or image.stem
    case_id = args.case_id or slugify(f"{title_name}-image-notice")
    source = {
        "url": args.source_url or "local-image",
        "agency": fields.get("agency") or "Unknown/needs verification",
        "captured_at": now_iso(),
        "input_type": "image",
        "image_path": str(image),
        "image_sha256": sha256_file(image),
        "ocr_status": "provided_text" if text else "needs_ocr_or_manual_review",
    }
    case = build_case(case_id, args.title or title_name, source, fields, text=text)
    paths = write_case_bundle(case, image)
    print(json.dumps({"case_id": case_id, "paths": paths, "ocr_status": source["ocr_status"], "external_actions_performed": False}, indent=2, ensure_ascii=False))


def cmd_validate(args: argparse.Namespace) -> None:
    case = read_json(Path(args.case))
    issues = []
    if not case.get("official_channels"):
        issues.append("missing official channels")
    if "Unknown" in (case.get("source", {}).get("agency") or ""):
        issues.append("agency/source needs verification")
    if not case.get("entities"):
        issues.append("missing entities")
    if not case.get("constraints"):
        issues.append("missing constraints")
    print(json.dumps({
        "case_id": case.get("case_id"),
        "valid_for_research": not issues,
        "issues": issues,
        "external_actions_performed": False,
    }, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pistalab", description="PistaLab lawful reward-intelligence CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("intake-text", help="Create case from notice text or a text file")
    p.add_argument("--text", default="")
    p.add_argument("--file", default="")
    p.add_argument("--title", default="")
    p.add_argument("--case-id", default="")
    p.add_argument("--source-url", default="")
    p.set_defaults(func=cmd_intake_text)

    p = sub.add_parser("intake-image", help="Create case from image plus optional extracted text")
    p.add_argument("image")
    p.add_argument("--text", default="", help="OCR/extracted text if available")
    p.add_argument("--title", default="")
    p.add_argument("--case-id", default="")
    p.add_argument("--source-url", default="")
    p.set_defaults(func=cmd_intake_image)

    p = sub.add_parser("source-check", help="Verify an official public source URL for a case")
    p.add_argument("case")
    p.add_argument("--url", default="")
    p.add_argument("--evidence-text", default="", help="Trusted extracted text from an official page fetch when direct fetch is blocked")
    p.add_argument("--evidence-file", default="", help="File containing extracted text from official page")
    p.set_defaults(func=cmd_source_check)

    p = sub.add_parser("search-plan", help="Build a lawful public-source search plan for a case")
    p.add_argument("case")
    p.set_defaults(func=cmd_search_plan)

    p = sub.add_parser("capture-evidence", help="Run allowed public search-plan queries and save local evidence ledger")
    p.add_argument("case")
    p.add_argument("--plan", default="")
    p.add_argument("--max-queries", type=int, default=0)
    p.add_argument("--per-query", type=int, default=5)
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--fetch-pages", action="store_true", help="Fetch public result pages and store redacted excerpts")
    p.add_argument("--excerpt-chars", type=int, default=2500)
    p.add_argument("--report-limit", type=int, default=12)
    p.set_defaults(func=cmd_capture_evidence)

    p = sub.add_parser("graph-score", help="Build entity graph and confidence score from evidence ledger")
    p.add_argument("case")
    p.add_argument("--ledger", default="")
    p.set_defaults(func=cmd_graph_score)

    p = sub.add_parser("hypotheses", help="Generate lawful public lead hypotheses from graph/score evidence")
    p.add_argument("case")
    p.add_argument("--ledger", default="")
    p.add_argument("--score", default="")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_hypotheses)

    p = sub.add_parser("run-hypotheses", help="Run allowed hypothesis queries, trace evidence, update case memory, and analyze leads")
    p.add_argument("case")
    p.add_argument("--hypotheses", default="")
    p.add_argument("--hypothesis-id", default="")
    p.add_argument("--top", type=int, default=2)
    p.add_argument("--max-queries-per-hypothesis", type=int, default=3)
    p.add_argument("--per-query", type=int, default=4)
    p.add_argument("--max-basis-per-hypothesis", type=int, default=3)
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--fetch-pages", action="store_true")
    p.add_argument("--excerpt-chars", type=int, default=2500)
    p.add_argument("--trace-id", default="")
    p.add_argument("--refresh", action="store_true", help="Refresh graph score and hypotheses after trace")
    p.set_defaults(func=cmd_run_hypotheses)

    p = sub.add_parser("tip-packet", help="Draft a review-only tip/research packet; no submission")
    p.add_argument("case")
    p.add_argument("--mode", default="research-summary", choices=["research-summary", "potential-tip-review"])
    p.set_defaults(func=cmd_tip_packet)

    p = sub.add_parser("sherlock-plan", help="Plan safe Sherlock username checks for official aliases; does not execute Sherlock")
    p.add_argument("case")
    p.add_argument("--allowed-only", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_sherlock_plan)

    p = sub.add_parser("court-deepen", help="Deepen public court-record context from official/public sources")
    p.add_argument("case")
    p.add_argument("--ledger", default="")
    p.add_argument("--run-search", action="store_true", help="Run safe public search queries; otherwise trace known official basis only")
    p.add_argument("--max-queries", type=int, default=0)
    p.add_argument("--per-query", type=int, default=4)
    p.add_argument("--delay", type=float, default=0.5)
    p.set_defaults(func=cmd_court_deepen)

    p = sub.add_parser("docket-find", help="Find public docket/case-number candidates without PACER/private/sealed access")
    p.add_argument("case")
    p.add_argument("--ledger", default="")
    p.add_argument("--max-queries", type=int, default=8)
    p.add_argument("--per-query", type=int, default=4)
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--threshold", type=int, default=75)
    p.add_argument("--report-limit", type=int, default=10)
    p.set_defaults(func=cmd_docket_find)

    p = sub.add_parser("source-router", help="Route case to public record sources and flag blocked/private sources")
    p.add_argument("case")
    p.add_argument("--ledger", default="")
    p.add_argument("--ready-only", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--probe", action="store_true", help="Probe ready public URLs only; no private/paid/sealed access")
    p.add_argument("--probe-limit", type=int, default=5)
    p.add_argument("--delay", type=float, default=0.5)
    p.set_defaults(func=cmd_source_router)

    p = sub.add_parser("sherlock-run", help="Gated Sherlock username correlation runner; preview by default")
    p.add_argument("case")
    p.add_argument("--plan", default="")
    p.add_argument("--username", action="append", default=[])
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--site", action="append", default=[])
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("--process-timeout", type=int, default=600)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--confirm", default="")
    p.add_argument("--browse", action="store_true", help="Prohibited; present only to block unsafe attempts")
    p.set_defaults(func=cmd_sherlock_run)

    p = sub.add_parser("sherlock-triage", help="Triage Sherlock weak username matches into corroboration priorities")
    p.add_argument("case")
    p.add_argument("--plan", default="")
    p.add_argument("--ledger", default="")
    p.add_argument("--threshold", type=int, default=70)
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_sherlock_triage)

    p = sub.add_parser("sherlock-corroborate", help="Corroborate triaged Sherlock matches using search snippets only")
    p.add_argument("case")
    p.add_argument("--triage", default="")
    p.add_argument("--max-queries", type=int, default=10)
    p.add_argument("--per-query", type=int, default=5)
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--strong-threshold", type=int, default=70)
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_sherlock_corroborate)

    p = sub.add_parser("camera-router", help="Route safe public/official camera sources; blocks open/private cameras")
    p.add_argument("case")
    p.set_defaults(func=cmd_camera_router)

    p = sub.add_parser("camera-search", help="Search public camera-source leads by snippets only; no live viewing/tracking")
    p.add_argument("case")
    p.add_argument("--router", default="")
    p.add_argument("--max-queries", type=int, default=12)
    p.add_argument("--per-query", type=int, default=4)
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--threshold", type=int, default=70)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_camera_search)

    p = sub.add_parser("route-runner", help="Run ready public source/camera routes, capture excerpts/hashes, detect deltas")
    p.add_argument("case")
    p.add_argument("--kind", default="all", choices=["all", "public_record", "public_camera"])
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--excerpt-chars", type=int, default=2500)
    p.add_argument("--report-limit", type=int, default=25)
    p.add_argument("--include-camera", action="store_true")
    p.add_argument("--ensure-routers", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_route_runner)

    p = sub.add_parser("review-extractor", help="Extract actionable/monitor signals from route-runner captures")
    p.add_argument("case")
    p.add_argument("--route-run", default="")
    p.add_argument("--min-route-score", type=int, default=0)
    p.add_argument("--tiers", default="A_REVIEW_NOW,B_KEEP_MONITORING")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--preview-chars", type=int, default=500)
    p.add_argument("--refresh", action="store_true", help="Refresh graph/hypotheses only if actionable signals are found")
    p.set_defaults(func=cmd_review_extractor)

    p = sub.add_parser("beyond-router", help="Route beyond-official public OSINT sources; blocks leaks/doxxing/private data")
    p.add_argument("case")
    p.set_defaults(func=cmd_beyond_router)

    p = sub.add_parser("beyond-search", help="Search beyond-official public sources by snippets only")
    p.add_argument("case")
    p.add_argument("--router", default="")
    p.add_argument("--route-id", action="append", default=[])
    p.add_argument("--max-queries", type=int, default=18)
    p.add_argument("--per-query", type=int, default=5)
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_beyond_search)

    p = sub.add_parser("beyond-extract", help="Fetch top beyond-official public results and extract artifacts/derived queries")
    p.add_argument("case")
    p.add_argument("--search", default="")
    p.add_argument("--max-results", type=int, default=5)
    p.add_argument("--excerpt-chars", type=int, default=12000)
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--query-report-limit", type=int, default=30)
    p.set_defaults(func=cmd_beyond_extract)

    p = sub.add_parser("beyond-derived-search", help="Run public searches from beyond-extract derived artifact queries")
    p.add_argument("case")
    p.add_argument("--extract", default="")
    p.add_argument("--artifact-type", action="append", default=[])
    p.add_argument("--max-queries", type=int, default=16)
    p.add_argument("--per-query", type=int, default=5)
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_beyond_derived_search)

    p = sub.add_parser("html-report", help="Generate/update living HTML case report")
    p.add_argument("case")
    p.add_argument("--output", default="")
    p.set_defaults(func=cmd_html_report)

    p = sub.add_parser("validate", help="Validate case readiness for lawful research")
    p.add_argument("case")
    p.set_defaults(func=cmd_validate)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
