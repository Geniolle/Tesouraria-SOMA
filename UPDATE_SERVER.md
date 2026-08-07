# Atualizar Servidor com Novo Código

**Status:** GitHub atualizado ✅  
**Próximo:** Deploy em produção

---

## 🚀 Atualizar Servidor (5 minutos)

### SSH no Servidor

```bash
ssh appuser@seu-servidor.com
cd /home/appuser/AppExtrato
```

### Pull do GitHub

```bash
# 1. Parar serviço
sudo systemctl stop appextrato

# 2. Atualizar código
git pull origin master

# 3. Instalar novas dependências
source venv/bin/activate
pip install -r requirements.txt

# 4. Testar
python -m src.gmail_to_sheets.app run-once

# 5. Reiniciar
sudo systemctl start appextrato

# 6. Verificar
sudo systemctl status appextrato
sudo tail -f /var/log/appextrato/app.log
```

---

## ✅ Verificação

```bash
# Status (deve mostrar "active (running)")
sudo systemctl status appextrato

# Logs (deve mostrar execução a cada 1 minuto)
sudo tail -20 /var/log/appextrato/app.log

# Sem erros
grep ERROR /var/log/appextrato/app.log
```

---

## 📊 O que foi adicionado ao GitHub

- ✅ Orchestrador com scheduler (`app.py`)
- ✅ 5 services do Entradas completos
- ✅ Suite de testes (`test_entradas_process.py`)
- ✅ Documentação completa (3 guias)
- ✅ Configuração (`requirements.txt` atualizado)

---

## 🔄 Se Algo Der Errado

```bash
# Reverter para versão anterior
git reset --hard HEAD~1
git pull origin master

# Ver logs de erro
sudo journalctl -u appextrato -n 50

# Reiniciar
sudo systemctl restart appextrato
```

---

## ✨ Resultado Esperado

Após atualizar:
- Entradas roda **a cada 1 minuto** automaticamente
- Transfere de DÍZIMOS/OFERTAS → CONTAORDEM
- Marca FINANCE = "Transferido"
- Zero erros nos logs

**Sistema 100% automatizado!**

---

## 📞 Comandos Úteis

```bash
# Status
sudo systemctl status appextrato

# Logs (tempo real)
sudo tail -f /var/log/appextrato/app.log

# Restart
sudo systemctl restart appextrato

# Parar
sudo systemctl stop appextrato

# Iniciar
sudo systemctl start appextrato

# Ver últimas 24 horas
sudo journalctl -u appextrato --since "24 hours ago"
```

---

## ✅ Pronto!

Sistema atualizado e rodando automaticamente.

**Próximo:** Monitorar logs e validar transferências em Google Sheets.
