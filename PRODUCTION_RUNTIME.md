# Production Runtime

This project currently has a single active production runtime.

## Active Production

- Host: `opc@servidor-tesouraria`
- Project directory: `/home/opc/AppExtrato`
- Runtime: `systemd`
- Service name: `appextrato.service`
- Start command: `/home/opc/AppExtrato/venv/bin/python -m src.gmail_to_sheets.app run-scheduled`
- Scheduler: single central orchestrator tick every 60 seconds

## Role of Docker

Docker is available in the repository as a support path, not as the current production executor.

Use Docker for:

- local isolation during development;
- future container-based deployment experiments;
- reproducible builds when needed.

Do not treat Docker as the source of truth for the live server unless the server deployment is explicitly migrated.

## Related Files

- [`SERVER_PATH.md`](SERVER_PATH.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`DOCKER.md`](DOCKER.md)

## Operational Rule

If the production runtime changes from `systemd` to Docker, update this file and the related deployment docs in the same change.
