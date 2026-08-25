# Deployment Checklist

Use this checklist before pushing or deploying changes.

## Must Not Be Deployed

- `.env`
- `credentials/`
- `logs/`
- `data/`
- cache directories such as `__pycache__`, `.mypy_cache`, `.ruff_cache`, and `.pytest_cache`
- virtual environments such as `venv/` and `.venv/`

## Must Be Deployed

- `src/`
- `tests/`
- `pyproject.toml`
- `requirements.txt`
- `README.md`
- `DEPLOYMENT.md`
- `DOCKER.md`
- `PRODUCTION_RUNTIME.md`
- `SERVER_PATH.md`

## Pre-Deploy Checks

1. Confirm no credentials are tracked by git.
2. Confirm the working tree only contains expected changes.
3. Run the relevant tests.
4. Confirm the server runtime is still `systemd`.
5. Confirm documentation does not claim Docker is the current production executor.

## Quick Validation Commands

```bash
git status --short
pytest tests/unit/
python -m src.gmail_to_sheets.app run-once
```

