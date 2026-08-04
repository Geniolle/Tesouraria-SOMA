---
name: gmail-to-sheets
description: Skill for developing the Gmail-to-Sheets pipeline — discovery, OAuth, message selection, attachment processing, idempotent writes, and deduplication.
---

# gmail-to-sheets Skill

This skill guides development of the Gmail-to-Sheets application, a Python pipeline that discovers emails, processes attachments, validates data, and writes results to Google Sheets.

## Workflow Phases

### 1. Discovery (Investigation)
- Progressively test Gmail search queries with real account credentials.
- Confirm sender, attachment naming, frequency, and folder state.
- Document findings with examples (no sensitive content).
- Adjust queries based on actual results, not assumptions.

### 2. Architecture
- Maintain strict module separation: config → auth → clients → services → processors.
- Use type hints and dependency injection where it aids testability.
- Avoid premature abstraction; add interfaces only when real benefit emerges.
- Keep main.py minimal; use an orchestrator for flow control.

### 3. OAuth & Credentials
- Gmail: Use `google-auth-oauthlib` with desktop app flow.
- Sheets: Use a service account with JSON credentials (scoped to Sheets API only).
- Store paths in `.env`; never commit credential files.
- Validate credentials at startup; fail loudly if missing.

### 4. Message Selection & Attachment Processing
- Implement safe, deterministic queries (sender + has:attachment).
- Download only `.txt` MT940 files; skip duplicates by filename.
- Extract data from attachment content (parsing deferred to Phase 2).
- Log every action: search, download, skip, error.

### 5. Idempotent Writes
- Before writing to Sheets, validate data structure.
- Implement deduplication check (by transaction ID or content hash).
- Append or update only; never delete rows.
- Use batch operations to minimize API calls.
- Rollback partial writes if validation fails.

### 6. Testing
- Unit tests mock Gmail and Sheets clients.
- Integration tests (if any) use a separate test Spreadsheet.
- No real API calls in CI pipeline.
- Logs must not expose tokens or sensitive content.

## Key Constraints

- **One step at a time**: Do not skip to implementation without confirming discovery.
- **Type safety**: Use Python type hints throughout; run `mypy`.
- **No hardcoded values**: Everything variable belongs in config or `.env`.
- **Logging is mandatory**: Structured logs for debugging and audit trail.
- **Reversibility**: All operations must be undoable or idempotent.
- **No parallel processing**: Respect Gmail rate limits; process sequentially.

## When to Proceed

- ✓ Gmail queries tested and documented.
- ✓ Attachment structure confirmed.
- ✓ OAuth flow prototyped locally.
- ✓ Sheets structure designed.
- ✓ Deduplication logic sketched.
- ✓ All tests passing.
- ✓ No credentials in Git.

Then and only then move to the next phase.
