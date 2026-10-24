# Third-party components

The runtime uses only the Python standard library; no third-party runtime packages or copied competitor code are bundled. Python is distributed under the PSF License, and its sqlite3 module (where used) links SQLite, which is public domain. Python/SQLite remain system components rather than vendored project code.

Build tooling: setuptools (MIT). Optional development tooling: Ruff (MIT), build (MIT), packaging (Apache-2.0 OR BSD-2-Clause), pyproject-hooks (MIT), colorama (BSD-3-Clause, Windows). These are installed as tools, not copied into source or runtime wheels. GitHub Actions checkout and setup-python are MIT-licensed actions referenced by commit SHA. Their upstream license files remain with the respective tools. No images, datasets, or other third-party assets are included; examples are synthetic fixtures authored for this project.
