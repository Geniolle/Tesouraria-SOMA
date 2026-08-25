# Quick Start

Local setup:

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pytest
python -m src.gmail_to_sheets.app run-once
```

## Notes

- Put credentials under `credentials/`
- Create a `.env` file from `.env.example`
- Use `run-scheduled` only when the app is being supervised by the production service or a scheduler

## Related Docs

- [`README.md`](README.md)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)

