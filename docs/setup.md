# Vibe Coding Toolkit setup

## Scope and source

- Applied on: 2026-10-19
- Project root: `C:\workspace\Tesouraria-SOMA`
- Toolkit checkout: `$env:USERPROFILE\.vibe-coding-toolkit-setup\vibe-coding-toolkit`
- Toolkit revision: `790a895304e0c08b70a5b215c9d334f1c86b816c`
- Published Prompt 12: verified on 2026-10-19
- Mode: minimal compatible integration; no business, production, infrastructure, or credential changes

## Instruction hierarchy

1. Global: `$env:USERPROFILE\.codex\AGENTS.md`
2. Workspace: `C:\workspace\AGENTS.md`
3. Project: `AGENTS.md`
4. Claude bridge: `CLAUDE.md` imports the project instructions

The closest project instructions govern project-specific behavior. Global and workspace rules remain applicable where they do not conflict. `AGENTS.md` was preserved unchanged during setup.

## Documentation map

| Toolkit destination | Canonical project document |
|---|---|
| `README.md` | `README.md` |
| `PRODUCT.md` | `PRODUCT.md` |
| `AGENTS.md` | `AGENTS.md` |
| `CLAUDE.md` | `CLAUDE.md` |
| `docs/architecture.md` | `ARCHITECTURE.md` |
| `docs/design.md` | `docs/design.md` |
| `docs/onboarding.md` | `QUICK_START.md` and `docs/OAUTH_SETUP.md` |
| `docs/quality.md` | `docs/quality.md` |
| `docs/setup.md` | this file |

Deployment documents were not consolidated because they contain operational procedures outside this setup's safe scope.

## Environment decision

```text
Dependency/tool: pytest, pytest-cov, ruff, mypy
Type: Python development dependencies
Existing global installation: not used for project runtime dependencies
Existing project environment: .venv with Python 3.11.13
Required version: versions resolved by uv.lock
Can global installation be reused safely: no
Does project require isolation: yes
Chosen action: uv sync --extra dev --frozen --inexact
Reason: install locked development tools while preserving existing extraneous operational packages
```

The normal frozen sync was rejected because its preview would remove 23 installed packages. The `--inexact` preview removed none and installed only 15 locked development packages. The `uv.lock` SHA-256 before synchronization was `BEC402D0142C4132B44E5F01800AA5D498164421FE79BE56E86770E54E3657FE`.

## Applicable toolkit components

| Component | Decision | Evidence or reason |
|---|---|---|
| Superpowers | Reuse global | Loaded and used for brainstorming, specification, planning, and verification |
| Ponytail | Reuse global | Full mode limits setup to the smallest compatible change |
| Caveman | Reuse global | Concise Portuguese communication; normal prose in persisted documents |
| RTK | Reuse global | Global CLI and Codex instructions already installed |
| Context7 | Reuse global | MCP query tested without project data or secrets |
| Graphify | Configure locally | Global CLI reused; deterministic code-only graph, no external provider |
| gmail-to-sheets skill | Preserve local | Existing project-specific skill under `.agents/skills/` |
| Harness2 | Native adaptation | No official CLI, benchmark, provider, or paid model integration |
| Layered memory | Reuse existing | Project documents plus Codex memory; no Obsidian vault or custom server needed |
| Next.js/React/Vercel skills | Not applicable | Python background service, no Next.js or React |
| PostgreSQL skills | Not applicable | No PostgreSQL dependency or schema in this project |
| shadcn/UI/browser workflow | Not applicable | No graphical web interface |
| Sentry MCP/SDK | Not selected | Existing logging and monitoring remain canonical; no authorized Sentry project |
| GitHub CI repair skill | Available on demand | Existing GitHub Actions; no failing PR/CI repair requested during setup |
| Differential security review | Manual fallback | Reusable Prompt 13 source recorded; no code/security behavior changed |
| Artifact skills | Not applicable | No document, slide, spreadsheet artifact authoring requirement |

## Graphify

Configuration: `.graphifyignore`. Mode: local AST extraction with `--code-only`; no semantic LLM, API key, external service, global graph merge, watcher, or Git hook.

Build and query from the project root:

```powershell
$env:GRAPHIFY_NO_AUTO_REFRESH = "1"
graphify extract . --code-only --no-cluster
graphify diagnose multigraph --graph graphify-out\graph.json --directed
graphify query "How is the CONTAORDEM description sequence generated?" --graph graphify-out\graph.json --budget 800
graphify export html --graph graphify-out\graph.json
```

After material source changes, use `graphify update . --no-cluster` under the same local-only policy. Do not configure Graphify hooks or global graph merging for this project. The generated `graphify-out/` directory is ignored by Git and regenerated locally when the graph needs to be refreshed.

Generated on 2026-10-19 with Graphify 0.9.92:

- 135 code files detected; 45 documents intentionally skipped in code-only mode.
- 2,017 nodes and 4,464 raw edges.
- `graphify-out/graph.json`, `manifest.json`, and `graph.html` created.
- No graph source path matched `.env`, `credentials/`, `logs/`, `data/`, or `.venv`.
- A query about `CONTAORDEM` sequencing found `ContaOrdemSequenceService`, `build_descricao_soma`, `strip_sequence_suffix`, and their tests.
- Integrity diagnostic: zero missing or dangling endpoints; four self-loops and 80 directed same-endpoint multi-relation groups. Graphify reports that the post-build `DiGraph` represents 4,382 edges. Treat the graph as useful but not lossless for relation multiplicity.

## Quality evidence

The canonical commands are in [quality.md](quality.md). Baseline on 2026-10-19:

| Check | Result | Classification |
|---|---|---|
| Python compile | exit 0 | Passed |
| pytest collection | 259 tests | Passed; offline boundary selected |
| pytest | 259 passed in 13.80s | Passed |
| Ruff lint | 20 errors | Pre-existing; concentrated in untracked Apps Script work |
| Ruff format check | 85 files would be reformatted | Pre-existing repository formatting debt |
| mypy | 76 errors in 24 files | Pre-existing typing debt |

No automatic formatting, lint fix, typing fix, or business-code edit was applied.

## Harness maintenance

- Re-run the relevant quality gates after material changes.
- Rebuild or update Graphify when source structure changes materially.
- Re-run Prompt 12 only when updating the toolkit integration itself; routine sessions load `AGENTS.md`, this setup ledger, and task-relevant canonical documents.
- Use one bounded native Harness2 comparison only when an observed harness failure supplies a concrete candidate. Do not invent a change when the harness passes.
- Invoke that method from `docs/prompts/15-harness-improvement.md` in the recorded toolkit revision; use `docs/prompts/14-harness-evaluation.md` for disposable evaluation cases.
- Recheck the toolkit source when its pinned revision changes. Preserve project customizations and prevent duplicate skills, MCPs, hooks, and instructions.

## Final verification

| Capability | Evidence | Status |
|---|---|---|
| Global instructions | Global `AGENTS.md` loaded in the active Codex context | Validated |
| Workspace instructions | File exists at `C:\workspace\AGENTS.md`; loading was not independently observable in a fresh session | Configured, fresh-session check pending |
| Project instructions | Project `AGENTS.md` loaded; SHA-256 remained `BBC06A19EF0B98930B7773A248EA5B8A166F5F40AA95654FB628284DBDD2879F` | Validated |
| Superpowers | Brainstorming, specification, plan, and verification workflows executed | Validated |
| Ponytail/Caveman | Global skills discovered and their constraints applied | Validated in current session |
| RTK | `rtk git status --short` exited 0 | Validated |
| Context7 | Resolved `/astral-sh/uv` and queried frozen/inexact sync semantics | Validated |
| Graphify | Deterministic extraction, diagnostic, query, and HTML export completed | Validated with recorded integrity limitation |
| Local skill | `.agents/skills/gmail-to-sheets/SKILL.md` discovered and applied | Validated in current session |
| Development environment | Python 3.11.13 retained; dev tools installed; lock hash unchanged | Validated |
| Harness2 native method | An observed workspace-instruction visibility limitation had no compatible local candidate because `AGENTS.md` must remain unchanged | Recorded; no speculative change adopted |

The standard exact `uv sync` preview would have removed 23 existing packages. The adopted `--inexact` command preserved them. Context7 documentation and the installed CLI dry run both confirmed that decision.

No deployment, push, production access, Gmail/Sheets/Apps Script/SOMA call, migration, service, hook, scheduled automation, paid API, credential change, global configuration change, or infrastructure change occurred.
