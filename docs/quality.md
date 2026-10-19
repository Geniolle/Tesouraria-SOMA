# Quality and review

## Canonical local environment

Use the existing project environment. Do not recreate it or use packages from another project.

```powershell
.\.venv\Scripts\python.exe --version
uv sync --extra dev --frozen --inexact
```

`--inexact` is required because this checkout contains compatible operational packages outside the current project lock. Omitting it would remove those packages.

## Safe checks

These commands do not require Gmail, Google Sheets, Apps Script, SOMA, or production access:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest tests\unit tests\apps_script -q -p no:cacheprovider
```

Do not run the root `test_*.py` scripts as part of the default offline gate. Inspect and authorize their external boundaries first.

## Review protocol

- Define the exact diff or baseline before review.
- Review business/data boundaries, external writes, credential handling, error paths, and relevant tests.
- Never connect to production to make a local check pass.
- Distinguish pre-existing failures from regressions introduced by the current change.
- For a reusable read-only security review, execute only the `Prompt` block from `docs/prompts/13-security-review.md` in the toolkit revision recorded in [setup.md](setup.md), scoped to the repository or exact diff under review.

## Harness verification

For material changes to instructions or integrations, execute the `Prompt` block from `docs/prompts/15-harness-improvement.md` and select cases from `docs/07-harness-evaluation.md` or `docs/prompts/14-harness-evaluation.md` in the pinned toolkit checkout. Use the native adaptation only; record the client, permissions, inputs, commands, observed behavior, and limitations in [setup.md](setup.md). A single passing case is a smoke test, not a reliability claim.

## Current baseline

The 2026-10-19 setup run passed compilation and all 259 selected offline tests. Ruff lint, Ruff formatting, and mypy have recorded pre-existing debt; see [setup.md](setup.md). These failures are not waived and must not be hidden with broad ignores or automatic rewrites. Address them through separate, reviewed work that preserves behavior.
