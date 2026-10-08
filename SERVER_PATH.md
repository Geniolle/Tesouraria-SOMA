# Server Path

Reference for the current production server and deployment location.

## Server Details

- SSH host: `opc@servidor-tesouraria-v2`
- Remote project directory: `/home/opc/AppExtrato`
- Self-hosted runner location: `/home/github-runner/actions-runner-tesouraria`
- Dedicated runner user: `github-runner`
- Deployment pipeline: GitHub Actions self-hosted runner
- Production runtime: `systemd` service `appextrato.service`
- Current start command: `/home/opc/AppExtrato/venv/bin/python -m src.gmail_to_sheets.app run-scheduled`

## Official Deployment Flow

```
Pull Request -> CI -> Merge master -> GitHub Actions -> Self-hosted runner (servidor-tesouraria-v2) -> testes -> restart appextrato.service -> health check -> produção
```

## Related Deployment Docs

- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)
- [`UPDATE_SERVER.md`](UPDATE_SERVER.md)
