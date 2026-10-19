# Vibe Coding Toolkit Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permanently integrate the applicable Vibe Coding Toolkit capabilities into Tesouraria-SOMA without changing business behavior or production state.

**Architecture:** Reuse global tooling and the existing Python environment. Add only missing project context, deterministic Graphify configuration/output, and reproducible quality evidence while mapping existing canonical documentation instead of duplicating it.

**Tech Stack:** Python 3.11.13, uv, pytest, Ruff, mypy, Graphify, Markdown, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-19-vibe-toolkit-integration-design.md`

## Global Constraints

- Preserve `AGENTS.md`, business logic, architecture, credentials, production configuration, infrastructure, and existing tracked/untracked work.
- Reuse global tools; make no global configuration or installation changes.
- Reuse `.venv`; do not recreate it or update main dependencies.
- Run no external Gmail, Sheets, Apps Script, SOMA, production, deployment, migration, push, or paid-service action.
- Graphify must be local, deterministic, and code-only.
- Use toolkit revision `790a895304e0c08b70a5b215c9d334f1c86b816c` consistently.

## Review Focus

- A test module that performs network or production work during collection must be excluded and recorded.
- `uv sync` must not change `uv.lock` or replace Python 3.11.13.
- Graphify must not ingest `.env`, credentials, keys, logs, runtime data, or generated output.
- New documentation must link canonical sources instead of contradicting deployment or business rules.
- Existing untracked Apps Script files and tests must remain byte-for-byte untouched.

---

### Task 1: Context and documentation

**Files:**
- Create: `PRODUCT.md`
- Create: `CLAUDE.md`
- Create: `docs/design.md`
- Create: `docs/quality.md`
- Create: `docs/setup.md`
- Preserve: `AGENTS.md`, `ARCHITECTURE.md`, `QUICK_START.md`, `docs/OAUTH_SETUP.md`

**Interfaces:**
- Consumes: existing canonical project documentation and approved design.
- Produces: durable documentation map, quality commands, toolkit coverage ledger, and client bridge.

- [x] Write only missing documents with explicit links to canonical sources.
- [x] Validate Markdown links and scan for placeholders or contradictory commands.
- [x] Verify `AGENTS.md` hash is unchanged.

### Task 2: Development environment and baseline

**Files:**
- Preserve: `.venv`, `pyproject.toml`, `uv.lock`, `requirements.txt`
- Evidence: `docs/setup.md`

**Interfaces:**
- Consumes: locked dependency declarations.
- Produces: installed development gates in the existing environment and baseline results.

- [x] Record Python, uv, declared dependencies, installed distributions, and dry-run impact.
- [x] Run `uv sync --extra dev --frozen` only if the preview is compatible; otherwise preview and use `--inexact` to preserve existing packages.
- [x] Verify Python and `uv.lock` hash remain unchanged.
- [x] Inspect test collection boundaries before running offline checks.

### Task 3: Deterministic Graphify integration

**Files:**
- Create: `.graphifyignore`
- Create: `graphify-out/` generated evidence
- Modify: `docs/setup.md`

**Interfaces:**
- Consumes: global Graphify and the safe project code corpus.
- Produces: local graph, report, HTML, health evidence, and a queryable project map.

- [x] Configure exclusions and verify sensitive/runtime paths are excluded.
- [x] Run deterministic code-only extraction with no external provider.
- [x] Validate graph integrity and execute one real query.
- [x] Record coverage, freshness, versions, and limitations.

### Task 4: Quality gates and harness evidence

**Files:**
- Modify: `docs/quality.md`
- Modify: `docs/setup.md`

**Interfaces:**
- Consumes: installed dev tools, safe tests, instruction hierarchy, Graphify output.
- Produces: reproducible gate results and toolkit coverage matrix.

- [x] Run compile, Ruff lint, Ruff format check, mypy, and safe pytest commands.
- [x] Exercise RTK, Context7, local skill discovery, and Graphify query.
- [x] Apply one bounded native Harness2 comparison only if an observed harness failure has a safe local candidate; otherwise record no candidate was justified.
- [x] Classify every failure and pending item without changing business logic.

### Task 5: Integrated verification and review

**Files:**
- Modify: `docs/setup.md`
- Modify: `docs/quality.md`

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: final verified matrix and review disposition.

- [x] Re-run applicable checks and verify documentation links/configuration syntax.
- [x] Compare Git status, hashes, and diffs against the baseline.
- [x] Obtain an independent read-only review of the complete diff.
- [x] Resolve Important/Critical findings within scope; record lesser or blocked items.
- [x] Update the final coverage matrix with only fresh evidence.
