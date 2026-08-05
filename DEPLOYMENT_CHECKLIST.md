# Deployment Checklist

## ❌ O QUE NÃO DEVE SUBIR AO SERVIDOR

### Credentials & Secrets
- ❌ `.env` — Ficheiro com credenciais sensíveis
- ❌ `credentials/` — Ficheiros OAuth e service accounts
  - `credentials/gmail-client-secret.json`
  - `credentials/sheets-service-account.json`
  - `credentials/gmail-oauth-token.json` (gerado em runtime)
- ❌ `*.key`, `*.pem`, `*.ppk` — Chaves privadas SSH/SSL
- ❌ `oracle-key.*` — Chaves Oracle
- ❌ `ssh/` — Pasta com chaves SSH

**Verificar:**
```bash
git ls-files | grep -E "credentials|\.env|\.key|\.pem"
# Deve retornar vazio!
```

### Cache & Temp Files
- ❌ `__pycache__/` — Python bytecode
- ❌ `.mypy_cache/` — Cache do mypy
- ❌ `.ruff_cache/` — Cache do ruff
- ❌ `.pytest_cache/` — Cache do pytest
- ❌ `.coverage` — Relatório de coverage
- ❌ `*.pyc`, `*.pyo`, `*.pyd` — Ficheiros compilados Python
- ❌ `*.tmp`, `*.bak` — Ficheiros temporários
- ❌ `*.swp`, `*~` — Backups de editor

**Limpar:**
```bash
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".mypy_cache" -exec rm -rf {} +
find . -type d -name ".ruff_cache" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +
```

### Runtime Generated Files
- ❌ `logs/` — Ficheiros de log (gerados em runtime)
- ❌ `data/` — Ficheiros de dados baixados
- ❌ `.coverage` — Relatório de cobertura de testes
- ❌ `dist/`, `build/` — Artefatos de build

### IDE & Editor Files
- ❌ `.vscode/` — Configurações VS Code locais
- ❌ `.idea/` — Configurações PyCharm locais
- ❌ `*.swp`, `*.swo` — Swap files do Vim
- ❌ `.DS_Store` — Metadata macOS
- ❌ `Thumbs.db`, `desktop.ini` — Metadata Windows

### Virtual Environments
- ❌ `venv/`, `.venv/`, `env/` — Ambientes virtuais
- ❌ `ENV/` — Diretório de ambiente

**Verificar no servidor:**
```bash
# Não deve ter venv commitado
git ls-files | grep -E "venv|\.venv|/bin/|/lib/python"
# Deve retornar vazio!
```

### Local Development
- ❌ `.claude/` — Configurações locais do Claude Code
- ❌ `*.env.local` — Ficheiros .env locais
- ❌ `.env.production.local` — Overrides de produção locais

---

## ✅ O QUE DEVE SUBIR AO SERVIDOR

### Source Code
- ✅ `src/` — Código-fonte Python
- ✅ `tests/` — Suite de testes
- ✅ `pyproject.toml` — Configuração do projeto
- ✅ `setup.py` — Script de instalação (se necessário)
- ✅ `requirements.txt` — Dependências (alternativa a pyproject.toml)

### Configuration
- ✅ `.env.example` — Template de configuração
- ✅ `pyproject.toml` — Configuração do projeto e ferramentas
- ✅ `.mypy.ini` — Configuração do mypy (se separado)
- ✅ `.ruff.toml` ou config em `pyproject.toml` — Configuração do ruff

### Docker
- ✅ `Dockerfile` — Especificação da imagem
- ✅ `docker-compose.yml` — Orquestração
- ✅ `docker-compose.dev.yml` — Desenvolvimento
- ✅ `.dockerignore` — Otimização do build

### Documentation
- ✅ `README.md` — Documentação principal
- ✅ `QUICK_START.md` — Setup rápido
- ✅ `DEPLOYMENT.md` — Guia de deployment
- ✅ `TROUBLESHOOTING.md` — Troubleshooting
- ✅ `ARCHITECTURE.md` — Visão arquitetural
- ✅ `DOCKER.md` — Guia Docker
- ✅ `MATCHING_LOGIC.md` — Lógica de matching
- ✅ `DEPLOYMENT_CHECKLIST.md` — Este ficheiro
- ✅ `LICENSE` — Licença do projeto

### Git Configuration
- ✅ `.gitignore` — Regras de exclusão
- ✅ `.gitattributes` — Atributos de ficheiros (se necessário)

### Directory Structure
- ✅ `logs/` — Diretório (será criado em runtime)
- ✅ `data/` — Diretório (será criado em runtime)
- ✅ `credentials/` — Diretório (será criado em runtime)

---

## 📋 Pré-Deployment Checklist

### Segurança
- [ ] Nenhum `.env` commitado
- [ ] Nenhuma credencial em `src/`
- [ ] Verificar `git ls-files | grep -i secret`
- [ ] Verificar `git ls-files | grep -i password`
- [ ] Verificar `git log --all --full-history | grep -i secret`

### Limpeza
- [ ] `rm -rf __pycache__ .mypy_cache .ruff_cache .pytest_cache`
- [ ] `find . -type d -name __pycache__ -exec rm -rf {} +`
- [ ] Verificar nenhuma pasta de venv commitada
- [ ] Verificar nenhum ficheiro `.log` commitado

### Documentação
- [ ] README.md atualizado
- [ ] Instruções de setup claras
- [ ] Variáveis de ambiente documentadas
- [ ] Troubleshooting atualizado

### Tests
- [ ] `pytest` passa localmente
- [ ] `ruff check src/` passa
- [ ] Verificar mypy status (39 erros conhecidos)

### Code Quality
- [ ] `ruff check src/ --fix` executado
- [ ] Imports organizados
- [ ] Type hints adicionadas onde possível
- [ ] Docstrings presentes em públicos APIs

---

## 🚀 Commands Before Pushing

```bash
# 1. Limpar caches
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +
find . -type d -name ".mypy_cache" -exec rm -rf {} +
find . -type d -name ".ruff_cache" -exec rm -rf {} +

# 2. Verificar git status
git status
git status --short

# 3. Verificar nenhuma credencial
git diff --cached | grep -i "password\|secret\|key\|token"
git diff --cached | grep -i "aws_\|api_key"

# 4. Verificar ficheiros ignorados
git check-ignore -v .env credentials/ logs/ data/

# 5. Rodar testes
pytest tests/unit/

# 6. Verificar linting
ruff check src/

# 7. Fazer commit (se necessário)
git add -A
git commit -m "Pre-deployment cleanup"

# 8. Verificar commits
git log --oneline -5

# 9. Push to remote
git push origin master
```

---

## 📊 Tamanho do Repositório

```bash
# Verificar tamanho
du -sh .git/
git count-objects -v

# Ficheiros rastreados
git ls-files | wc -l

# Ficheiros maiores
git ls-files | xargs -I {} ls -la {} | sort -k5 -rn | head -20
```

---

## ⚠️ Restaurar Ficheiro Acidentalmente Commitado

Se acidentalmente commitar credenciais:

```bash
# 1. IMEDIATAMENTE: Remover do histórico (purga completa)
git filter-branch --tree-filter 'rm -f credentials/*.json' HEAD

# 2. Force push (cuidado!)
git push origin master --force

# 3. Verificar
git log --all --full-history -- credentials/

# 4. Rotacionar credenciais (CRÍTICO!)
# Gerar novas chaves OAuth e service accounts
```

---

## 🔐 Security Reminders

1. **Nunca commitar credenciais** — Use `.env.example` como template
2. **Revisar antes de push** — `git diff --cached` antes de commit
3. **Usar `.gitignore` agressivamente** — Verifique antes de `git add .`
4. **Rotacionar credenciais regularmente** — Especialmente se forem leakadas
5. **Audit histórico** — `git log --all --full-history` para verificar leaks

---

## ✨ Resultado

Se seguir este checklist, o servidor receberá:
- ✅ Código-fonte limpo
- ✅ Sem credenciais sensíveis
- ✅ Sem ficheiros temporários/cache
- ✅ Documentação completa
- ✅ Pronto para deployment

