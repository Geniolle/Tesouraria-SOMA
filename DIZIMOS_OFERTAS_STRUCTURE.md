# Estrutura da Sheet DÍZIMOS/OFERTAS

**Spreadsheet ID:** 1poVWJGSBb13_2S1YKEzvFmkB9Ru0ZVzfQ0OEcMkfOZw  
**Total de Colunas:** 17

## Mapeamento de Colunas

| Índice | Nome da Coluna | Tipo | Observações |
|--------|---|---|---|
| 1 | , mas o processo é o | String | ⚠️ Nome estranho - pode ser corrompido no cabeçalho |
| 2 | MÊS | String | Ex: "JANEIRO" |
| 3 | DIA DA SEMANA | String | Ex: "QUARTA-FEIRA" |
| 4 | DATA | String (DD/MM/YYYY) | Ex: "03/01/2024" |
| 5 | TIPO | String | Ex: "DÍZIMOS/OFERTAS" |
| 6 | DOC. SOMA | String/Número | Ex: "4606815" (sequencial) |
| 7 | NÚMERO DOCUMENTO | String | Ex: "R240103" |
| 8 | VALOR | Decimal | Ex: "29,50" (comma as decimal) |
| 9 | RECIBO | String | Geralmente vazio |
| 10 | AUXILIAR TESOURARIA1 | String | Geralmente vazio |
| 11 | AUXILIAR TESOURARIA2 | String | Geralmente vazio |
| 12 | AUXILIAR SUBSTITUTO | String | Geralmente vazio |
| 13 | FINANCE | String | **VALIDAÇÃO:** Deve estar vazio para transferência |
| 14 | COMENTÁRIOS | String | Geralmente vazio |
| 15 | ID_INTERNO | String | Ex: "ENT0000000001" - **JÁ TEM ID!** |
| 16 | IDUSER | String | Geralmente vazio |
| 17 | TIMESTAMP | String | Geralmente vazio |

---

## Dados de Amostra

```
DATA       TIPO              DOC.SOMA  NÚMERO DOC  VALOR    FINANCE  DOC.SOMA  ID_INTERNO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
03/01/2024 DÍZIMOS/OFERTAS   4606815   R240103     29,50    [vazio]  4606815   ENT0000000001
07/01/2024 DÍZIMOS/OFERTAS   4606816   R240107     312,20   [vazio]  4606816   ENT0000000002
10/01/2024 DÍZIMOS/OFERTAS   4606817   R240110     83,25    [vazio]  4606817   ENT0000000003
14/01/2024 DÍZIMOS/OFERTAS   4606818   R240114     203,74   [vazio]  4606818   ENT0000000004
```

---

## Critérios de Validação para Transferência

Com base no script JavaScript e nos dados analisados:

✅ **Deve ser transferido se:**
- `TIPO` = "DÍZIMOS/OFERTAS" (ou "DIA VERBO MISSÔES")
- `DOC. SOMA` está **VAZIO** (deve ser limpo APÓS transferência)
- `FINANCE` está **VAZIO**
- `VALOR` > 0
- `DATA` existe e é válida

❌ **NÃO transferir se:**
- Qualquer um dos critérios acima não for atendido
- Registro já existe em CONTAORDEM (deduplicação por data+valor)

---

## Campos para Transferência

### Mapeamento DÍZIMOS/OFERTAS → CONTAORDEM

```
DÍZIMOS/OFERTAS           →  CONTAORDEM
────────────────────────     ──────────────────────
[4] DATA                  →  DATA MOV.
[7] NÚMERO DOCUMENTO      →  DESCRIÇÃO (parte de)
[8] VALOR                 →  IMPORTÂNCIA
[5] TIPO                  →  (sempre "Entrada")
                          →  PLANO DE CONTA (fixo: "DOAÇÕES - DÍZIMOS E OFERTAS")
                          →  CENTRO DE CUSTO (fixo: "10.10.01 - DÍZIMOS E OFERTAS")
                          →  PROCESSO (fixo: "DÍZIMOS/OFERTAS")
                          →  PERÍODO (extrair de DATA)
                          →  FORMA DE PAGAMENTO (fixo: "DINHEIRO")
                          →  CAIXA (fixo: "CAIXA DIÁRIO")
[15] ID_INTERNO           →  ID_INTERNO (copiar)
```

---

## Observações Importantes

1. **ID_INTERNO já existe!**
   - A sheet DÍZIMOS/OFERTAS já tem IDs sequenciais: ENT0000000001, ENT0000000002, etc.
   - Não precisa gerar novos IDs
   - Apenas copiar para CONTAORDEM

2. **DOC. SOMA será preenchido**
   - JavaScript preenche com número sequencial após transferência
   - Isso marca como "já transferido"
   - Próximas execuções não transferem registros com DOC.SOMA preenchido

3. **FINANCE é campo de validação**
   - Deve estar vazio para qualificar para transferência
   - Provavelmente usado por outro sistema

4. **Deduplicação**
   - Usar chave: `DATA + VALOR + DESCRIÇÃO`
   - Comparar contra CONTAORDEM para evitar duplicatas

---

## Questões para Clarificar

- [ ] Coluna 1 tem nome estranho - é erro de importação ou correto?
- [ ] Campo DOC.SOMA deve ser atualizado APÓS transferência? (como faz o JS)
- [ ] Campo STATUS em CONTAORDEM precisa ser preenchido?
- [ ] Existe matching com CONSTANTES ou dados vêm prontos?
