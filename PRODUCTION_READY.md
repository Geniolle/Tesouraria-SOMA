# 🚀 Production Ready - AppExtrato

**Status:** ✅ PRONTO PARA DEPLOY  
**Data:** 2026-08-06  
**Tempo de Deployment:** ~30 minutos

---

## ⚡ Deploy Imediato (3 Passos)

### Passo 1: Validação Local
```bash
python test_entradas_process.py
python -m src.gmail_to_sheets.app run-once
timeout 2m python -m src.gmail_to_sheets.app run-scheduled
```

### Passo 2: Prepare o Servidor

**SSH:**
```bash
ssh appuser@seu-servidor.com
cd /home/appuser/AppExtrato
```

**Dependências:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Configuração:**
```bash
nano .env                      # Preencher com valores de produção
mkdir -p credentials/
# Copiar 3 arquivos JSON para credentials/
```

### Passo 3: Iniciar em Produção

**Opção A: Systemd (Recomendado)**
```bash
# 1. Criar serviço (copie do arquivo DEPLOY.md)
sudo systemctl start appextrato
sudo systemctl enable appextrato

# 2. Monitorar
sudo tail -f /var/log/appextrato/app.log
```

**Opção B: Docker**
```bash
docker-compose up -d
docker-compose logs -f appextrato
```

---

## ✅ Verificação Pós-Deploy

```bash
# 1. Serviço rodando
sudo systemctl status appextrato
# RESULTADO: active (running)

# 2. Logs (deve mostrar a cada 1 minuto)
sudo tail -20 /var/log/appextrato/app.log
# RESULTADO: "[1/6] Authenticating..." (a cada minuto)

# 3. Google Sheets (verificar manualmente)
# - DÍZIMOS/OFERTAS: FINANCE = "Transferido" ✓
# - CONTAORDEM: Novos registros ✓

# 4. Sem erros
grep ERROR /var/log/appextrato/app.log
# RESULTADO: (nada - 0 erros)
```

---

## 📦 Arquivos Entregues

| Arquivo | Tipo | Status |
|---------|------|--------|
| `app.py` | Código | ✅ Novo |
| `processes/entradas/` | Código | ✅ 5 services |
| `test_entradas_process.py` | Testes | ✅ Suite completa |
| `INTEGRATION_GUIDE.md` | Docs | ✅ Completo |
| `DEPLOY.md` | Docs | ✅ Completo |
| `CLI_REFERENCE.md` | Docs | ✅ Completo |
| `requirements.txt` | Config | ✅ Atualizado |

---

## 🎯 O que Fazer Agora

1. **Hoje (30 min):**
   - Executar testes locais ✓
   - Deploy em produção ✓

2. **Primeira Hora:**
   - Monitorar logs
   - Validar transferências em Google Sheets

3. **Primeiras 24 Horas:**
   - Observar execuções (a cada 1 minuto)
   - Confirmar FINANCE sendo marcado
   - Confirmar registros em CONTAORDEM

---

## 📊 Resultado Esperado

**Automação completa:**
```
DÍZIMOS/OFERTAS (entrada manual)
        ↓
   [SCHEDULER - A CADA 1 MINUTO]
        ↓
   [Validação + Dedup + Transfer]
        ↓
CONTAORDEM (saída automática)
        ↓
FINANCE marcado como "Transferido"
```

**Sem intervenção manual!**

---

## 🔗 Documentação

Para detalhes completos, ver:
- **DEPLOY.md** — Instruções passo a passo
- **INTEGRATION_GUIDE.md** — Arquitetura e troubleshooting
- **CLI_REFERENCE.md** — Todos os comandos

---

## 💚 Pronto!

Sistema 100% funcional e pronto para produção.

**Tempo total: 30 minutos do SSH ao "active (running)"**

Boa sorte! 🚀
