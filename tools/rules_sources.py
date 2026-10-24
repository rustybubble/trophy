#!/usr/bin/env python3
"""Fetch, checksum and extract the pinned official TT sources; offline by default.

Use the bundled Python (pypdf) or install pypdf in a local isolated environment.
PDFs and extracted full text stay in ignored data/local/rules; the manifest and
rule inventory are reviewable source metadata. Optional 403s are recorded honestly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    {
        "id": "ittf-statutes-2026",
        "file": "2026_Statutes_v1_consolidated_clean.pdf",
        "url": (
            "https://documents.ittf.sport/sites/default/files/public/2026-02/2026_Statutes_v1_consolidated_clean.pdf"
        ),
        "edition": "54th edition, effective 1 January 2026",
        "required": True,
    },
    {
        "id": "hmo-18-2026",
        "file": "hmo-18-2026.pdf",
        "url": "https://www.ittf.com/wp-content/uploads/2026/02/HMO-18th-edition-February-2026.pdf",
        "edition": "18th edition February 2026 (index verified; full text blocked)",
        "required": False,
    },
    {
        "id": "ittf-documents",
        "file": "ittf-documents.html",
        "url": "https://www.ittf.com/committees/umpires-referees/documents/",
        "edition": "Index checked 2026-10-24",
        "required": False,
    },
    {
        "id": "ttr-2025",
        "file": "ttr-2025.html",
        "url": (
            ""
            "https://www.ittf.com/2025/04/13/enhanced-table-tennis-review-system-to-feature-at-ittf-mens-and-womens-world-cup-macao-2025/"
        ),
        "edition": "Official announcement; rendered date 13 May 2025; URL path 13 April 2025",
        "required": False,
    },
]
# Exact retrieved PDF; deliberate edition changes must update this pin and tests.
PINNED_STATUTES_SHA256 = "e55780dd20492253992dd6911a232d1a758c9660833672cb3a5d978a147e8671"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--refresh", action="store_true", help="Fetch public official URLs; otherwise use cached files only")
    p.add_argument("--cached-only", action="store_true", help="Explicit offline mode (default)")
    p.add_argument("--cache", type=Path, default=ROOT / "data/local/rules")
    args = p.parse_args()
    if args.refresh and args.cached_only:
        p.error("--refresh and --cached-only are mutually exclusive")
    args.cache.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "docs/rules/source-manifest.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    previous_rows = {s["id"]: s for s in previous.get("sources", [])}
    rows, errors = [], []
    now = datetime.now(UTC).isoformat()
    for spec in SOURCES:
        old = previous_rows.get(spec["id"], {})
        row = {**old, **spec}
        dest = args.cache / spec["file"]
        if args.refresh:
            try:
                data = urllib.request.urlopen(spec["url"], timeout=45).read()
                if spec["file"].endswith(".pdf") and not data.startswith(b"%PDF-"):
                    raise ValueError("Not a PDF response")
                if spec["required"] and hashlib.sha256(data).hexdigest() != PINNED_STATUTES_SHA256:
                    raise ValueError("Official PDF changed; inspect effective edition before updating the pin")
                dest.write_bytes(data)
                row["retrieved_at_utc"] = now
            except Exception as exc:
                row.update(status="blocked", error=str(exc), attempted_at_utc=now)
        if dest.exists():
            data = dest.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if spec["required"] and digest != PINNED_STATUTES_SHA256:
                raise ValueError("Cached statute checksum does not match the pinned edition")
            row.update(
                status="cached",
                sha256=digest,
                bytes=len(data),
                local_path=str(dest.relative_to(ROOT)) if dest.is_relative_to(ROOT) else str(dest),
            )
            row.setdefault("retrieved_at_utc", old.get("retrieved_at_utc", "2026-10-24"))
        else:
            row.setdefault("status", old.get("status", "not_cached"))
            if old.get("error") and "error" not in row:
                row["error"] = old["error"]
            if spec["required"]:
                errors.append(f"Required cache missing: {spec['file']}; run --refresh")
        rows.append(row)
    if not errors:
        from pypdf import PdfReader

        logging.getLogger("pypdf").setLevel(logging.ERROR)
        reader = PdfReader(args.cache / SOURCES[0]["file"])
        all_pages = [p.extract_text() for p in reader.pages]
        full = "\n\n".join(f"PRINTED PAGE {i + 1}\n{text}" for i, text in enumerate(all_pages))
        chapter = "\n\n".join(all_pages[38:45])
        regs = "\n\n".join(all_pages[51:57])
        for name, text in [
            ("statutes-extracted.txt", full),
            ("chapter-2.txt", chapter),
            ("match-officials-regulations.txt", regs),
        ]:
            (args.cache / name).write_text(text)
        # Every numbered Chapter-2 clause, including exceptions and containers.
        clauses = re.split(r"(?<![\d.])(2\.\d+(?:\.\d+)*)(?![\d.])\s+", chapter)
        parsed = []
        for i in range(1, len(clauses) - 1, 2):
            rule, text = clauses[i], clauses[i + 1].strip()
            # Cross-references inside prose are not clause starts: headings and
            # content starts occur after a period, newline, or a section heading.
            if text and rule not in {r["rule_id"] for r in parsed}:
                parsed.append({"rule_id": rule, "text": text, "source_id": "ittf-statutes-2026"})
        (args.cache / "chapter-2-clauses.json").write_text(json.dumps(parsed, indent=2) + "\n")
        rows[0]["extracted_files"] = {
            name: hashlib.sha256((args.cache / name).read_bytes()).hexdigest()
            for name in (
                "statutes-extracted.txt",
                "chapter-2.txt",
                "match-officials-regulations.txt",
                "chapter-2-clauses.json",
            )
        }
    manifest = {
        "profile": "ittf-2026-01-01+ttr-2025-upward-chord-v1",
        "checked_on": "2026-10-24",
        "sources": rows,
        "full_playing_laws_read": not bool(errors),
        "hmo_full_text_read": False,
        "verification_note": {
            "path": "docs/rules/source-verification.md",
            "sha256": hashlib.sha256((ROOT / "docs/rules/source-verification.md").read_bytes()).hexdigest(),
        },
        "license_note": (
            "ITTF Statutes front matter encourages reproduction with attribution. Source "
            "files remain local; no handbook redistribution permission is assumed."
        ),
        "amendment_status": (
            "Official documents index and official 2026 listing checked. Demo intentionally "
            "pinned to 1 January 2026 edition; no claim of exhaustive later-amendment certification."
        ),
        "errors": errors,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "errors": errors,
                "sources": [{k: r.get(k) for k in ["id", "status", "sha256"]} for r in rows],
            },
            indent=2,
        )
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
