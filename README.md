# redirect-inventory-audit

Audit a permanent redirect CSV **before a website migration goes live**. Check retired-route coverage and final destination inventory, find cycles/ambiguous sources, and export a passing map as one-hop redirects. Fully offline; Python standard library only.

[中文说明](README.zh-CN.md) · [Exact-route contract](docs/DESIGN.md)

A redirect can point to a syntactically valid path that does not exist in the new site. A clean map can also omit half the old site. Given old/current route inventories, this tool catches both problems without needing either website to be online.

## Install

Requires Python 3.10+. From a clone:

```sh
git clone https://github.com/KanadeK/redirect-inventory-audit.git
cd redirect-inventory-audit
python -m venv .venv
```

Activate with `source .venv/bin/activate` on macOS/Linux or `.venv\Scripts\Activate.ps1` in Windows PowerShell, then `python -m pip install .`. An activation-free checkout command is `python -m redirect_inventory_audit`. The v0.1.0 GitHub Release includes a wheel for `python -m pip install <downloaded-wheel.whl>`. No PyPI availability is claimed.

## Complete demo

```sh
redirect-inventory-audit examples/good.csv --old-paths examples/old.txt --new-paths examples/new.txt --flatten flattened.csv --json
redirect-inventory-audit examples/bad.csv --json
```

The first exits `0` and writes:

```csv
source,target,status
/old-guide,/docs/start,301
/guide,/docs/start,301
/legacy-api,/docs/api,308
```

The old `/still-live` route is present in the current inventory, so it needs no redirect. The second command exits `1` with cycle, duplicate-source and self-redirect findings. Repeating the first command with the same output filename exits `2` and preserves that file. Use a new output name to export again.

## CSV and inventories

CSV headers must be exactly `source,target` or `source,target,status` in that order. The two-column form uses status `301`. Supported explicit statuses are `301` and `308`. Inputs must be UTF-8, optional BOM. NUL and overly large fields are rejected. Malformed record widths are reported as validation failures.

Inventories are plain UTF-8 text, one route per line. Blank lines and lines starting with `#` are ignored; surrounding whitespace is not silently trimmed. Current inventory entries represent **served pages**, not intermediate redirect sources. Duplicate inventory lines are deduplicated. Paths can be generated from your site's route manifest; the tool does not crawl sites or parse XML sitemaps.

- With `--new-paths`, every internal terminal destination must be present and no redirect source may also be a current served page.
- With both inventories, each route in `old - current` must have a redirect entry. Its chain must also pass all other checks. `--old-paths` requires `--new-paths`.
- Coverage counts are set membership, not proof that the live site serves a page or that its content is equivalent. External destinations require an explicit allowlist and cannot be checked against a local served-path list.

## Origin and URL policy

By default, sources and local targets use rooted routes such as `/old?lang=en`. Preserve exact case, trailing slash, query ordering and percent spelling; `/A`, `/a`, `/a/`, `/a?x=1` and `/%61` are separate strings. No percent decoding or Unicode normalization is used for matching. Decoding is used only to reject dot segments and encoded path controls/backslashes. Your inventories must use the same representation as your routing configuration.

```sh
redirect-inventory-audit redirects.csv --origin https://example.org --allow-origin https://docs.example.org --new-paths current.txt --json
```

With `--origin`, absolute URLs on that origin are converted to rooted routes, including query strings. Host case, IDNA names and default ports are normalized for origin comparisons. Other absolute targets require a matching `--allow-origin` (repeatable); comparison includes scheme, host and port. An allowlist entry allows that entire origin, not just one path. External URLs are treated as terminal destinations; the tool never follows them. Without `--origin`, an absolute URL is external, even if you consider it your own site.

Credentials in URLs, fragments, raw whitespace/control characters, backslashes, malformed percent escapes, relative paths, protocol-relative URLs and dot segments are rejected. Only HTTP(S) absolute URLs are supported. Regexes, prefix/wildcard rules and server-specific rewrites are not interpreted. Literal strings that resemble patterns must not be used to model pattern-based routing.

## Chain and export behavior

Cycles and self-redirects fail. Every repeated source fails, even if both targets agree. Incoming paths to an ambiguous or invalid source also fail. Chains with only one status type can be flattened; a chain mixing 301 and 308 fails conservatively because collapsing it can change method handling. Temporary redirect statuses are outside this version's model.

Export occurs only when the **entire audit passes**, includes every accepted source, retains its status, and refuses existing files. Audit/validation failures never create an output. Ordinary write exceptions remove a newly created partial output when possible. Export is not a transaction with a web server and is not advertised as crash-atomic; review and deploy using your normal workflow.

Exit `0`: completed, no findings. Exit `1`: completed with validation findings, no export. Exit `2`: input/parser/I/O/argument/resource-limit error, or output already exists. JSON stdout has `schema_version: 1`, complete counts, limited finding/route samples, omitted counts and inventory statistics. JSON operational errors go to stderr; argparse retains its normal usage output. Terminal output escapes input strings. Reports and exported paths may contain private route/query data; inspect them before sharing.

Defaults: at most 32 MiB per map/inventory, 50,000 data records per map and lines per inventory, 8,192 characters per CSV field/route, and 100 sampled findings/routes. `--max-bytes`, `--max-rows`, `--max-findings`, and `--max-routes` adjust the corresponding limits. Metadata and inventories are held in memory; this is an operational guard, not a hard memory/time sandbox. The graph walk is iterative and memoized, so a long chain does not consume Python recursion depth or materialize every full chain. Python API calls change and restore the process-wide CSV field limit; concurrent threaded calls are unsupported.

## Alternatives and boundaries

[redirect-map-lint](https://github.com/aamirtechs/redirect-map-lint) already checks offline maps and offers automatic normalization/cleanup. This project adds explicit old/current inventory invariants, exact route matching, origin policies, conservative status checks, bounded JSON reports and all-or-nothing validation before export. [LinkCanary](https://github.com/LinkCanary/LinkCanary) and [lychee](https://github.com/lycheeverse/lychee) check live links. Use a live checker after deployment: this tool cannot predict CDN, browser, rewrite, application or server behavior, verify target availability, or judge content equivalence.

## Verify, uninstall and cleanup

```sh
python -m pip install . ruff==0.17.2 build==1.6.1
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m build
python -m pip uninstall redirect-inventory-audit
```

Tests include CLI/export flows, no-overwrite behavior, input byte preservation, inventory failures, origin/query rules, a 20,000-hop chain and seeded random graphs checked with an independent walk oracle. CI covers Linux/Windows/macOS and Python 3.10/3.13; inspect the actual Actions run for status. No settings or cache are stored. Remove your exported CSVs, downloaded artifacts and virtual environment when no longer needed; source files are unchanged.

MIT. [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Third-party notes](THIRD_PARTY.md)
