import contextlib
import csv
import io
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from redirect_map_audit.core import InputError, analyze, origin_key


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "map.csv"

    def make(self, rows, header=("source", "target", "status")):
        with self.path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)
        return self.path

    def paths(self, name, lines):
        target = self.root / name
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target

    def test_valid_map_and_complete_retired_coverage(self):
        self.make([("/old", "/middle", "301"), ("/middle", "/new", "301")])
        old = self.paths("old.txt", ["/old", "/still"])
        new = self.paths("new.txt", ["/new", "/still"])
        original = self.path.read_bytes()
        with patch("socket.socket", side_effect=AssertionError("network request")):
            result = analyze(self.path, old_paths=old, new_paths=new)
        self.assertTrue(result.report["ok"])
        self.assertEqual(1, result.report["chains"])
        self.assertEqual(1, result.report["inventory"]["retired"])
        self.assertEqual(original, self.path.read_bytes())

    def test_uncovered_old_route_and_missing_terminal(self):
        self.make([("/old", "/ghost", "301")])
        result = analyze(
            self.path,
            old_paths=self.paths("old", ["/old", "/lost"]),
            new_paths=self.paths("new", ["/real"]),
        )
        self.assertEqual(
            {"missing-destination": 1, "uncovered-old-path": 1}, result.report["counts"]
        )

    def test_source_must_not_also_be_a_current_page(self):
        self.make([("/old", "/new", "301")])
        result = analyze(self.path, new_paths=self.paths("new", ["/old", "/new"]))
        self.assertEqual({"source-is-current": 1}, result.report["counts"])

    def test_cycle_incoming_chain_and_self_redirect(self):
        self.make(
            [
                ("/in", "/a", "301"),
                ("/a", "/b", "301"),
                ("/b", "/a", "301"),
                ("/self", "/self", "301"),
            ]
        )
        result = analyze(self.path)
        self.assertEqual(
            {"cycle": 1, "self-redirect": 1, "unresolved-chain": 1}, result.report["counts"]
        )
        self.assertEqual("cycle", result.resolved["/in"][3])

    def test_duplicate_source_blocks_incoming_paths(self):
        for second in ("/b", "/c"):
            self.make([("/in", "/a", "301"), ("/a", "/b", "301"), ("/a", second, "301")])
            report = analyze(self.path).report
            self.assertEqual(1, report["counts"]["duplicate-source"])
            self.assertEqual(1, report["counts"]["unresolved-chain"])

    def test_mixed_status_chain_refuses_flatten(self):
        self.make([("/a", "/b", "301"), ("/b", "/c", "308")])
        result = analyze(self.path)
        self.assertEqual({"mixed-status-chain": 1}, result.report["counts"])
        with self.assertRaises(InputError):
            result.flatten(self.root / "flat.csv")
        self.assertFalse((self.root / "flat.csv").exists())

    def test_homogeneous_308_chain_keeps_status(self):
        self.make([("/a", "/b", "308"), ("/b", "/c", "308")])
        result = analyze(self.path)
        target = self.root / "flat.csv"
        result.flatten(target)
        with target.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual({"source": "/a", "target": "/c", "status": "308"}, rows[0])

    def test_export_never_overwrites_existing_file(self):
        result = analyze(self.make([("/a", "/b", "301")]))
        with self.assertRaises(FileExistsError):
            result.flatten(self.path)
        self.assertEqual(
            "/a",
            next(csv.DictReader(io.StringIO(self.path.read_text(encoding="utf-8-sig"))))["source"],
        )

    def test_exact_case_slash_query_and_percent_semantics(self):
        self.make(
            [
                ("/A", "/end", "301"),
                ("/a", "/other", "301"),
                ("/a/", "/last", "301"),
                ("/x?one=1", "/x?one=2", "301"),
                ("/%61", "/last", "301"),
            ]
        )
        result = analyze(self.path)
        self.assertTrue(result.report["ok"])
        self.assertEqual(5, result.report["route_count"])
        self.assertEqual("/other", result.resolved["/a"][0])
        self.assertEqual("/x?one=2", result.resolved["/x?one=1"][0])

    def test_same_origin_urls_and_default_ports(self):
        self.make([("https://EXAMPLE.org:443/old", "https://example.org/new?", "301")])
        result = analyze(self.path, origin="https://example.org")
        self.assertTrue(result.report["ok"])
        self.assertEqual("/new?", result.resolved["/old"][0])

    def test_external_targets_require_exact_origin_allowlist(self):
        for target in (
            "https://docs.example.org/page",
            "https://docs.example.org:444/page",
            "http://docs.example.org/page",
        ):
            self.make([("/old", target, "301")])
            result = analyze(self.path, allow_origins=["https://docs.example.org"])
            self.assertEqual(target == "https://docs.example.org/page", result.report["ok"])

    def test_external_absolute_targets_are_terminal(self):
        self.make([("/a", "/b", "301"), ("/b", "https://other.example/end", "301")])
        result = analyze(
            self.path, allow_origins=["https://other.example"], new_paths=self.paths("new", [])
        )
        self.assertTrue(result.report["ok"])
        self.assertEqual("https://other.example/end", result.resolved["/a"][0])

    def test_url_credentials_and_invalid_routes(self):
        for target in (
            "javascript:alert(1)",
            "//evil.example/x",
            "/a/../b",
            "/%2e%2e/b",
            "/path#fragment",
            "/bad%ZZ",
            "/x%00",
            "https://user:pass@other.example/x",
            "/back\\slash",
            "/space here",
        ):
            with self.subTest(target=target):
                self.make([("/old", target, "301")])
                self.assertIn("invalid-target", analyze(self.path).report["counts"])

    def test_source_scope_and_unsupported_status(self):
        self.make([("https://other.example/a", "/new", "301"), ("/old", "/new", "302")])
        self.assertEqual(
            {"invalid-source": 1, "unsupported-status": 1}, analyze(self.path).report["counts"]
        )

    def test_origin_validation_and_port_zero(self):
        self.assertNotEqual(origin_key("https://example.org:0"), origin_key("https://example.org"))
        self.make([("/a", "/b", "301")])
        for origin in (
            "https://example.org/path",
            "https://example.org?",
            "file:///x",
            "https://bad%host",
            "",
        ):
            with self.assertRaises(ValueError):
                analyze(self.path, origin=origin)
        self.assertEqual(origin_key("https://[::1]"), ("https", "::1", 443))

    def test_two_column_map_defaults_to_301(self):
        result = analyze(self.make([("/old", "/new")], header=("source", "target")))
        self.assertTrue(result.report["ok"])
        self.assertEqual("301", result.edges["/old"][1])

    def test_bounded_samples_keep_complete_counts(self):
        self.make([(f"/a{i}", "/end", "302") for i in range(10)])
        report = analyze(self.path, max_findings=1, max_routes=2).report
        self.assertEqual(10, report["finding_count"])
        self.assertEqual(9, report["omitted_findings"])
        self.assertEqual(8, report["omitted_routes"])

    def test_size_row_and_positive_limits(self):
        self.make([("/a", "/b", "301"), ("/c", "/d", "301")])
        for options in (
            {"max_rows": 1},
            {"max_bytes": 1},
            {"max_routes": 0},
            {"max_findings": True},
        ):
            with self.assertRaises(InputError):
                analyze(self.path, **options)

    def test_invalid_inventory_and_old_without_new(self):
        self.make([("/a", "/b", "301")])
        old = self.paths("old", ["/a"])
        with self.assertRaises(InputError):
            analyze(self.path, old_paths=old)
        with self.assertRaises(InputError):
            analyze(self.path, new_paths=self.paths("bad", ["/bad path"]))

    def test_malformed_headers_csv_utf8_and_nul(self):
        for data in (
            b"wrong,header\n",
            b'source,target\n"unterminated',
            b"source,target\n/a,/\xff\n",
            b"source,target\n/a,/\x00\n",
        ):
            self.path.write_bytes(data)
            with self.assertRaises(InputError):
                analyze(self.path)

    def test_ragged_row_is_reported(self):
        self.make([("/a", "/b", "301", "extra")])
        self.assertEqual({"row-width": 1}, analyze(self.path).report["counts"])

    def test_large_chain_without_recursion(self):
        self.make([(f"/r{i}", f"/r{i + 1}", "301") for i in range(20_000)])
        result = analyze(self.path, max_routes=1)
        self.assertTrue(result.report["ok"])
        self.assertEqual(20_000, result.resolved["/r0"][1])
        self.assertEqual("/r20000", result.resolved["/r0"][0])

    def test_random_graph_against_independent_walk_oracle(self):
        rng = random.Random(37)
        for _ in range(40):
            graph = {f"/n{i}": f"/n{rng.randrange(23)}" for i in range(20)}
            self.make([(a, b, "301") for a, b in graph.items()])
            result = analyze(self.path)
            for source in graph:
                seen, node = set(), source
                while node in graph and node not in seen:
                    seen.add(node)
                    node = graph[node]
                final = None if node in seen else node
                self.assertEqual(final, result.resolved[source][0])

    def test_cli_export_and_failure_does_not_create_output(self):
        self.make([("/old", "/new", "301")])
        flat = self.root / "flat.csv"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "redirect_map_audit",
                str(self.path),
                "--flatten",
                str(flat),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertTrue(flat.is_file())
        self.make([("/loop", "/loop", "301")])
        blocked = self.root / "blocked.csv"
        result = subprocess.run(
            [sys.executable, "-m", "redirect_map_audit", str(self.path), "--flatten", str(blocked)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertFalse(blocked.exists())

    def test_operational_errors_and_terminal_escaping(self):
        from redirect_map_audit.cli import main

        self.make([("/old\x1b[31m", "/new", "301")])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(1, main([str(self.path)]))
        self.assertNotIn("\x1b", output.getvalue())
        self.path.write_text("bad")
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            self.assertEqual(2, main([str(self.path)]))
        self.assertNotIn("Traceback", error.getvalue())
