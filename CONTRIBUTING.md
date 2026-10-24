# Contributing

Discuss substantial changes in an issue first. Keep the tool offline and keep its documented input semantics stable. Add a regression test that demonstrates the user-visible bug. Do not submit real customer data, credentials or large generated fixtures.

Use Python 3.10 or later in a virtual environment:

```sh
python -m pip install . ruff==0.17.2 build==1.6.1
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m build
```

CI runs checks and builds only; it never commits code. Changes are reviewed and committed by the repository owner. Copyright and licenses of any proposed third-party material must be preserved. No automated dependency-update bot is configured.
