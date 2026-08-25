# Server Path

Reference for the current production server and deployment location.

## Server Details

- SSH host: `opc@servidor-tesouraria`
- Remote project directory: `/home/opc/AppExtrato`
- Current deployed commit: `a26c352`
- Last verified sync date: `2026-08-25`
- Production runtime: `systemd` service `appextrato.service`
- Current start command: `/home/opc/AppExtrato/venv/bin/python -m src.gmail_to_sheets.app run-scheduled`

## Related Deployment Docs

- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PUSH_ORACLE.md`](PUSH_ORACLE.md)
- [`UPDATE_SERVER.md`](UPDATE_SERVER.md)

## Notes

- The server path above is the canonical remote location for deploy and operational checks.
- If the host name `servidor-tesouraria` or the directory changes in the real environment, update this file and the related deploy docs together.
