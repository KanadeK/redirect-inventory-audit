"""Exact-route migration checks. No network access, server emulation or regex rules."""

from __future__ import annotations

import csv
import ipaddress
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


class InputError(ValueError):
    pass


def origin_key(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise InputError("absolute URLs require http(s), a hostname and no user information")
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = ipaddress.IPv6Address(host).compressed
    elif any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in host.split(".")
    ):
        raise InputError("invalid hostname")
    port = (
        parsed.port
        if parsed.port is not None
        else (443 if parsed.scheme.lower() == "https" else 80)
    )
    return parsed.scheme.lower(), host, port


def site_origin(value):
    if not value or any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        raise InputError("origin contains invalid characters")
    key = origin_key(value)
    parsed = urlsplit(value)
    if (
        parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
    ):
        raise InputError("origin must contain only scheme and authority")
    return key


def route(value, *, source, site=None, allowed=frozenset()):
    if (
        not value
        or len(value) > 8192
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
        or "\\" in value
    ):
        raise InputError("route has whitespace, controls, backslash or excessive length")
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise InputError("invalid percent escape")
    parsed = urlsplit(value)
    if "#" in value:
        raise InputError("fragments are outside the exact-route model")
    decoded = unquote(parsed.path)
    if (
        any(p in (".", "..") for p in decoded.split("/"))
        or any(ord(c) < 32 or ord(c) == 127 for c in decoded)
        or "\\" in decoded
    ):
        raise InputError("dot segments or encoded control/backslash in path")
    if parsed.scheme or parsed.netloc:
        key = origin_key(value)
        if site is not None and key == site:
            had_query = "?" in value
            value = parsed.path or "/"
            if had_query:
                value += "?" + parsed.query
        elif source:
            raise InputError("source must be rooted or belong to --origin")
        elif key not in allowed:
            raise InputError("external target origin is not explicitly allowed")
        else:
            return value
    if not value.startswith("/") or value.startswith("//") or urlsplit(value).netloc:
        raise InputError("local route must start with one slash")
    return value


def _size_guard(path, max_bytes):
    if Path(path).stat().st_size > max_bytes:
        raise InputError("input exceeds max-bytes; audit not completed")


def inventory(path, site, max_rows, max_bytes):
    _size_guard(path, max_bytes)
    result = set()
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        for number, line in enumerate(stream, 1):
            if number > max_rows:
                raise InputError("inventory exceeds max-rows (including blank/comment lines)")
            text = line.rstrip("\r\n")
            if not text or text.startswith("#"):
                continue
            try:
                result.add(route(text, source=True, site=site))
            except ValueError as exc:
                raise InputError(f"invalid inventory route at line {number}: {exc}") from exc
    return result


@dataclass
class Audit:
    report: dict
    edges: dict
    resolved: dict

    def flatten(self, output):
        """Export only a completely passing map; never overwrite an existing path."""
        if not self.report["ok"]:
            raise InputError("refusing to export a map with validation errors")
        target = Path(output)
        created = False
        try:
            with target.open("x", encoding="utf-8", newline="") as stream:
                created = True
                writer = csv.writer(stream)
                writer.writerow(["source", "target", "status"])
                for source, (_, status, _) in self.edges.items():
                    writer.writerow([source, self.resolved[source][0], status])
        except BaseException:
            if created:
                target.unlink(missing_ok=True)
            raise


def analyze(
    path,
    *,
    old_paths=None,
    new_paths=None,
    origin=None,
    allow_origins=(),
    max_rows=50_000,
    max_bytes=32 * 1024**2,
    max_findings=100,
    max_routes=100,
):
    for value in (max_rows, max_bytes, max_findings, max_routes):
        if type(value) is not int or value <= 0:
            raise InputError("limits must be positive integers")
    if old_paths is not None and new_paths is None:
        raise InputError("--old-paths requires --new-paths so retired routes can be determined")
    site = site_origin(origin) if origin is not None else None
    allowed = frozenset(site_origin(v) for v in allow_origins)
    old = inventory(old_paths, site, max_rows, max_bytes) if old_paths is not None else None
    new = inventory(new_paths, site, max_rows, max_bytes) if new_paths is not None else None
    _size_guard(path, max_bytes)
    counts = Counter()
    findings = []
    edges = {}
    blocked = {}
    records = 0

    def emit(code, source, record=0, **extra):
        counts[code] += 1
        if len(findings) < max_findings:
            findings.append({"code": code, "source": source, "record": record, **extra})

    field_limit = csv.field_size_limit(8192)
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            if header not in (["source", "target"], ["source", "target", "status"]):
                raise InputError(
                    "CSV header must be source,target or source,target,status in that order"
                )
            for record, row in enumerate(reader, 2):
                records += 1
                if any("\x00" in field for field in row):
                    raise InputError("NUL is not supported in CSV input")
                if records > max_rows:
                    raise InputError("map exceeds max-rows; audit not completed")
                if len(row) != len(header):
                    emit("row-width", "", record)
                    continue
                try:
                    source = route(row[0], source=True, site=site)
                except ValueError as exc:
                    emit("invalid-source", row[0], record, reason=str(exc))
                    continue
                duplicate = source in edges
                if duplicate:
                    emit("duplicate-source", source, record, first_record=edges[source][2])
                    blocked[source] = "duplicate-source"
                status = row[2] if len(header) == 3 else "301"
                try:
                    target = route(row[1], source=False, site=site, allowed=allowed)
                except ValueError as exc:
                    emit("invalid-target", source, record, reason=str(exc))
                    target = None
                    blocked[source] = "invalid-target"
                if status not in ("301", "308"):
                    emit("unsupported-status", source, record)
                    blocked[source] = "unsupported-status"
                if source == target:
                    emit("self-redirect", source, record)
                    blocked[source] = "self-redirect"
                if not duplicate:
                    edges[source] = (target, status, record)
    except (csv.Error, UnicodeError) as exc:
        raise InputError(
            "CSV must be UTF-8 strict CSV with fields at most 8192 characters"
        ) from exc
    finally:
        csv.field_size_limit(field_limit)

    # Each source is resolved once. Memoized iterative walking avoids recursion
    # and copying a full route chain for every source.
    resolved = {}
    cycle_nodes = set()
    for source in edges:
        if source in resolved:
            continue
        trail, positions = [], {}
        node = source
        while True:
            if node in resolved:
                outcome = resolved[node]
                break
            if node in blocked:
                outcome = (None, None, 0, blocked[node])
                resolved[node] = outcome
                break
            if node not in edges:
                outcome = (node, 0, 0, None)
                break
            if node in positions:
                start = positions[node]
                cycle = trail[start:]
                emit("cycle", node, edges[node][2], members=cycle[:20], member_count=len(cycle))
                for member in cycle:
                    resolved[member] = (None, None, 0, "cycle")
                cycle_nodes.update(cycle)
                outcome = (None, None, 0, "cycle")
                trail = trail[:start]
                break
            positions[node] = len(trail)
            trail.append(node)
            node = edges[node][0]
        for member in reversed(trail):
            final, hops, mask, problem = outcome
            if problem is None:
                mask |= 1 if edges[member][1] == "301" else 2
                outcome = (final, hops + 1, mask, None)
            resolved[member] = outcome

    chains = 0
    sampled_routes = []
    for source, (target, status, record) in edges.items():
        final, hops, mask, problem = resolved[source]
        if problem and source not in blocked and source not in cycle_nodes:
            emit("unresolved-chain", source, record, reason=problem)
        if mask == 3:
            emit("mixed-status-chain", source, record)
        if hops is not None and hops > 1:
            chains += 1
        if new is not None and source in new:
            emit("source-is-current", source, record)
        if new is not None and final is not None and final.startswith("/") and final not in new:
            emit("missing-destination", source, record, target=final)
        if len(sampled_routes) < max_routes:
            sampled_routes.append(
                {
                    "source": source,
                    "target": target,
                    "status": status,
                    "final_target": final,
                    "hops": hops,
                    "problem": problem,
                }
            )
    retired = (old - new) if old is not None else set()
    uncovered = sorted(retired - edges.keys())
    for source in uncovered:
        emit("uncovered-old-path", source)
    count = sum(counts.values())
    report = {
        "schema_version": 1,
        "ok": count == 0,
        "records": records,
        "route_count": len(edges),
        "chains": chains,
        "finding_count": count,
        "counts": dict(sorted(counts.items())),
        "findings": findings,
        "omitted_findings": count - len(findings),
        "routes": sampled_routes,
        "omitted_routes": len(edges) - len(sampled_routes),
        "inventory": {
            "old": len(old) if old is not None else None,
            "current": len(new) if new is not None else None,
            "retired": len(retired) if old is not None else None,
            "unmapped_retired": len(uncovered) if old is not None else None,
        },
    }
    return Audit(report, edges, resolved)
