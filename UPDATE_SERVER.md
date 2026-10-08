# Update Server

This project uses an **automated deployment pipeline** powered by GitHub Actions and a self-hosted runner.

## Official Update Flow

The official way to update the production server is:

1. Open a **Pull Request** to `master`.
2. Wait for **CI** to validate unit tests and linter.
3. **Merge** to `master`.
4. The **Deploy Production** GitHub Actions workflow triggers automatically.
5. The **Self-Hosted Runner** on `servidor-tesouraria-v2` executes git pull, runs tests, restarts `appextrato.service`, and performs health checks with automatic rollback if health checks fail.

```
Pull Request
    ↓
CI
    ↓
Merge master
    ↓
GitHub Actions
    ↓
Self-hosted runner servidor-tesouraria-v2
    ↓
testes no servidor
    ↓
restart appextrato.service
    ↓
health check
    ↓
produção
```

See:

- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)
- [`SERVER_PATH.md`](SERVER_PATH.md)
