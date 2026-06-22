"""Command-line interface for tablecheck.

Usage::

    python -m tablecheck schema.json
    python -m tablecheck schema.json --quiet
    tablecheck schema.json            # if installed

Exit code is 0 when clean, 1 when any violation is found, 2 on usage error.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .core import load_schema, summarize, validate


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tablecheck",
        description="Validate referential integrity across related CSV/TSV tables.",
    )
    p.add_argument("schema", help="path to the JSON schema file")
    p.add_argument(
        "-q", "--quiet", action="store_true",
        help="print only the summary line, not each violation",
    )
    p.add_argument(
        "--max", type=int, default=0, metavar="N",
        help="print at most N violations (0 = no limit)",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        schema = load_schema(args.schema)
    except FileNotFoundError:
        print(f"tablecheck: schema not found: {args.schema}", file=sys.stderr)
        return 2
    except ValueError as exc:  # bad JSON
        print(f"tablecheck: invalid schema JSON: {exc}", file=sys.stderr)
        return 2

    violations = validate(schema)

    if not violations:
        print(f"OK: {len(schema.tables)} table(s) valid, 0 violations.")
        return 0

    if not args.quiet:
        shown = violations if args.max <= 0 else violations[: args.max]
        for v in shown:
            print(v)
        if args.max and len(violations) > args.max:
            print(f"... and {len(violations) - args.max} more")

    counts = summarize(violations)
    breakdown = ", ".join(f"{k}={n}" for k, n in sorted(counts.items()))
    print(f"FAIL: {len(violations)} violation(s) [{breakdown}]")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
