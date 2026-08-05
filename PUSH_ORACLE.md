# Push para Servidor Oracle - Instruções Finais

## ✅ Status GitHub

```
Remote: https://github.com/Geniolle/Tesouraria-SOMA.git
Push: ✅ CONCLUÍDO
Commit: 88d832d
Branch: master
Ficheiros: 57 (limpo e seguro)
```

## 🚀 Fazer Deploy no Servidor Oracle

### Via SSH (Opção Rápida)

```bash
ssh opc@servidor-tesouraria << 'DEPLOY'
cd /home/opc/AppExtrato
git fetch origin master
git reset --hard origin/master
source .venv/bin/activate
pip install -e .
python -m pytest tests/unit/test_config.py -q
echo "✅ DEPLOYMENT CONCLUÍDO"
DEPLOY
```

### Via Docker (Produção)

```bash
cd /home/opc/AppExtrato
git pull origin master
cp .env.example .env
# editar .env com credenciais
docker-compose up -d
docker-compose logs -f
```

### Manual

```bash
cd /home/opc/AppExtrato
git pull origin master
source .venv/bin/activate
pip install -e .
python -m pytest tests/unit/
```

## 📋 Enviado

✅ Código-fonte (src/)
✅ Testes (tests/)
✅ Docker (Dockerfile, docker-compose.yml)
✅ Documentação (9 ficheiros)
✅ .env.example (template)

❌ NÃO enviado: .env, credentials/, logs/, data/

## 🔐 Segurança

✅ 0 credenciais commitadas
✅ .gitignore atualizado
✅ Pronto para produção

## ✨ Status

**PRONTO PARA DEPLOYMENT**

Commit: 88d832d
Data: 2026-08-05
