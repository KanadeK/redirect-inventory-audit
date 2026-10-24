# v0.1.0

Initial inventory-aware offline permanent redirect auditor. Checks retired-route coverage, internal terminal destinations, live-page/source conflicts, duplicate sources, cycles, self-redirects, explicit external origins and conservative 301/308 chain semantics. Includes exact route matching, capped JSON samples with complete counts, non-overwriting one-hop CSV export, runnable examples, English/Chinese docs and MIT licensing.

Local validation: 25 unittest cases passed on Windows/Python 3.13, including a 20,000-hop chain and 40 seeded graphs checked by an independent walk oracle. Ruff, wheel/sdist builds, clean wheel installation and passing/failing README workflows are release gates, followed by all six Linux/Windows/macOS Python 3.10/3.13 CI jobs and sole-owner identity checks.

Limits: exact-match local CSV and plain-text inventories, permanent 301/308 only; no server rewrite/regex/prefix emulation, fragment handling, live requests, target availability or content verification. Route/query metadata is included in reports. Export is not a server deployment or a crash-atomic transaction. No PyPI publication is claimed.
