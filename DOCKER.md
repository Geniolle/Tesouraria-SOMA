# Docker Guide

Docker is available in this repository as a support path.
It is not the current production executor.

## What Docker Is For

- local isolation during development;
- reproducible builds;
- future migration experiments;
- running the app in a disposable environment.

## What Docker Is Not For Right Now

- the live server runtime;
- the source of truth for production execution;
- a replacement for the current `systemd` service.

## Local Build

```bash
docker build -t gmail-to-sheets .
```

## Local Run

```bash
docker run --rm \
  --env-file .env \
  -v $(pwd)/credentials:/app/credentials:ro \
  -v $(pwd)/logs:/app/logs \
  gmail-to-sheets
```

## Compose

The repository includes a `docker-compose.yml` for local or future container-based workflows.
The production server currently uses `systemd`, so compose is not the live runtime.

```bash
docker compose up -d
docker compose logs -f gmail-to-sheets
docker compose down
```

## Development Compose

`docker-compose.dev.yml` is the interactive development variant.

```bash
docker compose -f docker-compose.dev.yml run --rm gmail-to-sheets-dev
```

## Notes

- Keep credentials outside the image.
- Use the mounted `credentials/`, `data/`, and `logs/` directories.
- If production moves to containers later, update [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md) and [`DEPLOYMENT.md`](DEPLOYMENT.md) together.

