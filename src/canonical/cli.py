"""Command-line interface.

    python -m canonical.cli \
        --recruiter_csv data/sample/recruiter_export.csv \
        --ats_json     data/sample/ats_profile.json \
        --resume       data/sample/resume.pdf \
        --recruiter_notes data/sample/recruiter_notes.txt \
        --config configs/default.json \
        --explain

Point it at any subset of sources plus an optional config; it prints the
projected profile as JSON. ``--explain`` adds the provenance/confidence meta so
you can see exactly where every value came from and why.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .pipeline import run
from .project import canonical_view

SOURCE_FLAGS = ["recruiter_csv", "ats_json", "resume", "recruiter_notes"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="canonical", description="Multi-source candidate data transformer")
    for flag in SOURCE_FLAGS:
        p.add_argument(f"--{flag}", help=f"path to a {flag} source file")
    p.add_argument("--config", help="path to an output config JSON (default schema if omitted)")
    p.add_argument("--explain", action="store_true", help="include provenance + per-field confidence")
    p.add_argument("--out", help="write JSON output to this path instead of stdout")
    p.add_argument("-v", "--verbose", action="store_true", help="log per-source extraction info")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    sources = {flag: getattr(args, flag) for flag in SOURCE_FLAGS if getattr(args, flag)}
    if not sources:
        print("error: provide at least one source (e.g. --recruiter_csv ...)", file=sys.stderr)
        return 2

    config = json.loads(open(args.config, encoding="utf-8").read()) if args.config else {}
    result = run(sources, config)

    payload = result["profile"]
    if args.explain:
        payload = {"profile": result["profile"],
                   "explain": canonical_view(result["internal"])["_meta"],
                   "valid": result["valid"], "problems": result["problems"]}

    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text)
        print(f"wrote {args.out}")
    else:
        print(text)

    if not result["valid"]:
        print(f"\n[validation] {len(result['problems'])} problem(s):", file=sys.stderr)
        for prob in result["problems"]:
            print(f"  - {prob}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
