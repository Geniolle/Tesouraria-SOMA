# Vibe Coding Toolkit Integration Design

## Intent

Prepare Tesouraria-SOMA for permanent AI-assisted development using the applicable Vibe Coding Toolkit capabilities. Preserve business logic, production configuration, credentials, existing architecture, canonical documentation, and the current Git worktree.

## Scope

This integration is limited to project-owned development context, documentation, deterministic local code indexing, and development quality gates. It does not change application behavior, external APIs, deployment, infrastructure, production services, authentication, spreadsheet data, email state, Apps Script, or SOMA.

## Sources and baseline

- Toolkit source: local reference checkout at revision `790a895304e0c08b70a5b215c9d334f1c86b816c`, verified against the published Prompt 12 on 2026-10-19.
- Project runtime: Python 3.11.13 in the existing `.venv`.
- Dependency authority: `pyproject.toml` plus `uv.lock`; `requirements.txt` remains a production/CI compatibility input.
- Existing context: global `AGENTS.md`, workspace `C:\workspace\AGENTS.md`, and project `AGENTS.md`.
- Existing user work: preserve untracked `src/gmail_to_sheets/clients/apps_script/` and `tests/apps_script/`.

## Architecture

### Instruction hierarchy

The existing project `AGENTS.md` remains unchanged and authoritative for project-specific constraints. Global and workspace instructions remain external inputs. A minimal `CLAUDE.md` bridge points Claude-compatible clients to `AGENTS.md` without duplicating rules.

### Documentation map

The toolkit's nine destinations map to existing canonical documents where possible:

| Toolkit destination | Project source |
|---|---|
| `README.md` | Existing `README.md` |
| `PRODUCT.md` | New concise product boundary document |
| `AGENTS.md` | Existing `AGENTS.md`, unchanged |
| `CLAUDE.md` | New bridge to `AGENTS.md` |
| `docs/architecture.md` | Existing `ARCHITECTURE.md` |
| `docs/design.md` | New non-UI applicability record |
| `docs/onboarding.md` | Existing `QUICK_START.md` and `docs/OAUTH_SETUP.md` |
| `docs/quality.md` | New canonical quality and review guide |
| `docs/setup.md` | New toolkit inventory, evidence, coverage, and maintenance ledger |

Deployment documentation remains untouched. Its consolidation is outside this setup because it could alter operational procedures.

### Development environment

Reuse `.venv`; never recreate it. Inspect installed distributions and preview `uv sync --extra dev --frozen` before execution. If exact sync would remove existing compatible packages, use `uv sync --extra dev --frozen --inexact`. The selected sync may install only versions already resolved by `uv.lock`; it must not rewrite the lockfile or update main dependencies. Required development tools are pytest, pytest-cov, ruff, and mypy.

### Graphify

Reuse global Graphify 0.9.92. `.graphifyignore` excludes secrets, credentials, keys, environments, caches, logs, runtime data, generated output, vendored skills, Git internals, and operational artifacts. Extraction is code-only and deterministic. It must not use semantic extraction, API keys, external providers, Git hooks, watchers, or paid services.

Generated graph outputs are local project evidence, not source code. They are ignored by Git and regenerated when needed. The graph must receive an integrity check and at least one real query. Coverage, freshness, and limitations are recorded in `docs/setup.md`.

### Quality and safety

Only offline tests are allowed. Tests are inspected for network or production boundaries before execution. Root scripts named `test_*.py` are excluded until proven safe. Standard checks are compilation, Ruff lint, Ruff format check, mypy, and the safe test collection under `tests/`.

Failures are reported as baseline/pre-existing or introduced. No business logic is changed merely to make a check green.

### Toolkit coverage

Superpowers, Ponytail, Caveman, RTK, Context7, Graphify, and the local gmail-to-sheets skill are reused. Next.js, React, PostgreSQL, shadcn, Sentry, Vercel, and browser/UI integrations are inapplicable to this Python service. Harness2 uses only the native method adaptation; the official CLI and paid/model-backed benchmarks are not installed or run.

## Verification

- Instruction files are discoverable and their hierarchy is documented.
- Development dependencies resolve from the existing frozen lock.
- The lockfile hash remains unchanged after synchronization.
- Offline checks run with explicit commands and captured exit codes.
- Graphify produces a non-empty graph with a clean integrity diagnostic or a recorded limitation.
- RTK, Context7, skill discovery, and a graph query receive runtime evidence.
- Git status proves pre-existing untracked files remain present and no production/configuration files changed unexpectedly.

## Recovery

New documentation and Graphify configuration can be removed independently. Before modifying any existing project file, create a timestamped backup outside Git without secrets. Do not delete or overwrite user files. No production rollback is needed because this design performs no production action.
