# AGENTS.md — Regras Permanentes do Projeto

Este documento define as regras que orientam qualquer desenvolvimento no projeto `gmail-to-sheets`.

## Princípios Estruturais

1. **Arquitetura modular**: Separação clara entre autenticação, cliente Gmail, processamento e cliente Google Sheets.
2. **Sem código monolítico**: Cada responsabilidade num ficheiro/módulo próprio.
3. **Sem valores hardcoded**: Todas as variáveis dependentes do ambiente devem estar em `.env` ou `config.py` tipado.
4. **Proteção de credenciais**: Nenhum token, senha, chave privada ou credencial JSON entra no Git.

## Processo de Desenvolvimento

1. **Passo a passo**: Uma etapa de cada vez; não implementar tudo antecipadamente.
2. **Testes antes de merge**: Testes unitários e de integração devem passar localmente.
3. **Lint e type checking**: `ruff check`, `ruff format`, `mypy` devem passar.
4. **Revisão de código**: Antes de commit, revisar ficheiros alterados e credenciais.
5. **Mensagens claras de commit**: Explicar o quê e o porquê, não apenas o quê.

## Autenticação e Segurança

1. **OAuth 2.0 para Gmail**: Usar `google-auth-oauthlib` com fluxo de aplicação desktop.
2. **Service account para Sheets**: Usar JSON com permissões restritas (não admin).
3. **Credenciais isoladas**: Ficheiros de credenciais em `credentials/` (ignorados no Git).
4. **Variáveis sensíveis no `.env`**: Paths, IDs, secrets em variáveis de ambiente.
5. **Validação no arranque**: Falhar explicitamente se faltarem credenciais ou configurações obrigatórias.

## Google Sheets

1. **Escrita idempotente**: Validar antes de escrever; prevenir duplicações.
2. **Sem apagar**: Apenas append ou update de linhas existentes.
3. **Formatação segura**: Validar dados antes de escrever.

## Gmail

1. **Pesquisa progressiva**: Começar com filtros amplos; refinar conforme necessário.
2. **Arquivo pós-processamento**: Marcar e arquivar para evitar reprocessamento.
3. **Sem processamento em paralelo**: Respeitar rate limits do Gmail.
4. **Logs detalhados**: Registar cada ação (pesquisa, download, validação, escrita).

## Testes

1. **Mocks nas fronteiras**: Não fazer chamadas reais ao Gmail ou Sheets em testes unitários.
2. **Testes de integração isolados**: Se necessário, usar uma conta de teste ou fixtures.
3. **Sem fixtures do Gmail em CI**: Testes unitários devem rodar offline.

## Git e GitHub

1. **Sem `git add .` cego**: Sempre revisar com `git status` e `git diff` antes.
2. **Sem force push**: Nunca reescrever história pública.
3. **Sem amend a commits publicados**: Fazer novo commit em vez de corrigir.
4. **Branches feature**: `feature/`, `fix/`, `docs/` conforme apropriado.
5. **PRs com contexto**: Descrever o quê, o porquê e como testar.

## Logs e Debugging

1. **Estruturado**: Usar `logging` com níveis apropriados (DEBUG, INFO, WARNING, ERROR).
2. **Sem print()**: Exceto para CLI interativa e apenas onde apropriado.
3. **Arquivo de log**: Guardar em `logs/` com timestamp.
4. **Sem informação sensível**: Nunca logar tokens, keys ou conteúdo sensível integral.

## Compatibilidade

1. **Local primeiro**: Funcionar em VS Code (Windows/Mac/Linux) com Python 3.10+.
2. **Oracle Cloud depois**: Facilitar migração para Oracle Cloud (estrutura agnóstica a SO).
3. **Agendamento futuro**: Preparar para execução periodic (Scheduler, Cron, etc.).

## Alterações

Mudanças significativas de arquitetura devem ser documentadas num comment no ficheiro ou numa issue antes de implementação.
