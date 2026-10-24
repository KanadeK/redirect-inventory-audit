from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .core import analyze


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit exact permanent redirect maps and retired/current route coverage offline."
    )
    parser.add_argument("map")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--old-paths", help="old route inventory; requires --new-paths")
    parser.add_argument("--new-paths", help="current served route inventory")
    parser.add_argument("--origin", help="site origin used to resolve absolute same-site URLs")
    parser.add_argument(
        "--allow-origin",
        action="append",
        default=[],
        help="explicit external target origin; repeatable",
    )
    parser.add_argument(
        "--flatten", help="export passing map as one-hop CSV; refuses existing files"
    )
    parser.add_argument("--max-rows", type=int, default=50_000)
    parser.add_argument("--max-bytes", type=int, default=32 * 1024**2)
    parser.add_argument("--max-findings", type=int, default=100)
    parser.add_argument("--max-routes", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = analyze(
            args.map,
            old_paths=args.old_paths,
            new_paths=args.new_paths,
            origin=args.origin,
            allow_origins=args.allow_origin,
            max_rows=args.max_rows,
            max_bytes=args.max_bytes,
            max_findings=args.max_findings,
            max_routes=args.max_routes,
        )
        if args.flatten and result.report["ok"]:
            result.flatten(args.flatten)
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2
    report = result.report
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        print(
            f"Routes: {report['route_count']}; chains: {report['chains']}; findings: {report['finding_count']}"
        )
        for item in report["findings"]:
            print(json.dumps(item, ensure_ascii=True))
        if report["omitted_findings"]:
            print(f"Omitted findings: {report['omitted_findings']}; counts remain complete")
    return 0 if report["ok"] else 1
