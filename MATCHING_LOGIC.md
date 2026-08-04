# Lógica de Matching: JavaScript vs Python

## Fluxo do SelecionarDeParaSoma()

### **(0) SETUP E VALIDAÇÕES INICIAIS**
```
├─ Carrega sheets CONTAORDEM e CONSTANTES
├─ Valida timezone
└─ Inicializa auditoria (log detalhado)
```

### **(1) CABEÇALHOS + ÍNDICES DINÂMICOS**
```
├─ Lê headers de ambas as sheets
├─ Cria mapas: header → índice de coluna
└─ Permite refatoração sem quebrar código
```
**Implementação Python:** `_map_columns()` - mesmo conceito

### **(2) VALIDAÇÃO DE COLUNAS OBRIGATÓRIAS**
```
CONTAORDEM precisa:
  - DOC. SOMA (será preenchido)
  - DESCRIÇÃO (origem para matching)
  - TIPO (Entrada/Saída)
  - IMPORTÂNCIA (valor)
  - DESCRIÇÃO SOMA (será gerada)
  - DATA MOV. (data da transação)

CONSTANTES precisa:
  - TEXTO (padrão para match)
  - TIPO (Entrada/Saída)
  - DOC. SOMA (preenchimento)
  - DESCRIÇÃO SOMA (base sequencial)
  - VALOR (opcional, para validação)
  - TIMESTAMP (registro quando processado)
```
**Implementação Python:** `_validate_columns()` - validação equivalente

### **(3) CARREGAMENTO DE DADOS**
```
Lê TODAS as linhas em memória:
  - dadosCO: todas linhas de CONTAORDEM (exceto header)
  - dadosCT: todas linhas de CONSTANTES (exceto header)
```
**Implementação Python:** `_load_reference_data()`, `_prepare_with_matching()`

### **(3.1) CONTROLE DE SEQUENCIAL POR DIA**

**Estrutura de Estado:**
```javascript
seqState["2026-03-04||MONITORAMENTO"] = {
  used: {1: true, 2: true},      // Números já usados
  max: 2,                        // Próximo será 3
  baseExemplo: "MONITORAMENTO",  // Base da descrição
  diaExibicao: "04/03/2026"      // Data formatada
}
```

**Regra:**
```
Mesmo dia + mesma base descrição:
  31/07 | MONITORAMENTO N001  (já existe)
  31/07 | MONITORAMENTO N002  (já existe)
  31/07 | MONITORAMENTO N003  (novo, próximo)

Data diferente:
  01/08 | MONITORAMENTO N001  (reinicia!)
```

**Implementação Python:** 
```python
seq_state = {
    "dia_key||base_key": {
        "used": {1, 2},      # Set de números já usados
        "max": 2,            # Próximo = 3
        "base_example": "...",
        "day_display": "04/03/2026"
    }
}
```

### **(3.1.1) BUILD SEQUENTIAL STATE**

Primeira passagem em CONTAORDEM:
```javascript
dadosCO.forEach(row => {
  const descSoma = row[idxDescSomaCO];  // "MONITORAMENTO N002"
  const dataMov = row[idxDataMovCO];    // "31/07/2026"
  
  // Split: "MONITORAMENTO N002" → base: "MONITORAMENTO", n: 2
  const parsed = splitDescricaoSequencial(descSoma);
  
  // Carrega/cria estado para esse dia + base
  const state = ensureState(dataMov, parsed.base);
  
  // Marca como já utilizado
  state.used[2] = true;
  state.max = 2;
});
```

**Para que serve:**
- Evitar sobrescrita de sequenciais já existentes
- Continuar numeração correta se re-rodar
- Separar por dia (reset diário)

### **(4) PROCESSAMENTO + MATCH**

Para cada linha elegível em CONTAORDEM:

```javascript
// Etapa 1: Validar elegibilidade
if (!docSomaElegivel(docSomaAtual)) return;  // Pula se já tem valor
if (!obterChaveDia(dataMovCO_raw)) return;   // Pula se data inválida

// Etapa 2: Normalizar descrição CONTAORDEM
const descCO_norm = removerAcentos(descCO_raw).toUpperCase();
const tipoCO = String(linha[idxTipoCO]).trim().toUpperCase();
const valorCO = Number(linha[idxImportCO]);

// Etapa 3: Procurar match em CONSTANTES
for (let j = 0; j < dadosCT.length; j++) {
  const ct = dadosCT[j];
  
  // 3.1: Normalizar CONSTANTES
  const textoCT_norm = removerAcentos(ct[idxTextoCT]).toUpperCase();
  const tipoCT = String(ct[idxTipoCT]).trim().toUpperCase();
  const valorCT_raw = ct[idxValorCT];
  
  // 3.2: Validar critérios de match
  const textoOK = descCO_norm.includes(textoCT_norm) || 
                  textoCT_norm.includes(descCO_norm);
  
  const tipoOK = tipoCO === tipoCT;
  
  let valorOK = true;
  if (valorCT_raw !== "" && valorCT_raw !== null) {
    valorOK = Math.abs(valorCO - Number(valorCT_raw)) < 0.01;  // Diferença < 0,01
  }
  
  // 3.3: Se todos os critérios OK, preencher
  if (textoOK && tipoOK && valorOK) {
    // Gerar descrição com sequencial
    const descSomaFinal = gerarDescricaoComSequencialPorDia(
      ct[idxDescSomaCT],  // "MONITORAMENTO"
      dataMovCO_raw       // "31/07/2026"
    );
    
    // Preencher linha CONTAORDEM
    linha[idxDescSomaCO] = descSomaFinal;       // "MONITORAMENTO N003"
    linha[idxDocSomaCO] = ct[idxDocSomaCT];     // "SOMA-001"
    
    // Copiar campos adicionais
    colunasParaCopiar.forEach(col => {
      linha[idxCO(col)] = ct[idxCT(col)];
    });
    
    // Atualizar timestamp em CONSTANTES
    dadosCT[j][idxTimestampCT] = agora;
    
    // Log de auditoria
    auditoria.sucessos++;
    matchEncontrado = true;
    break;  // Sair do loop, encontrou match
  }
}

// Se não encontrou match
if (!matchEncontrado) {
  auditoria.falhas++;
  // Log detalhado de por que falhou
}
```

### **(5) GRAVAÇÃO**

```javascript
// Escrever dados atualizados em CONTAORDEM
sheetCO.getRange(2, 1, dadosCO.length, lastColCO).setValues(dadosCO);

// Escrever coluna de timestamp em CONSTANTES
const colTimestamp = dadosCT.map(row => [row[idxTimestampCT]]);
sheetCT.getRange(2, idxTimestampCT + 1, dadosCT.length, 1).setValues(colTimestamp);
```

**Batching:** Escreve em 2 batch calls (1 por sheet)

### **(6) ORDENAÇÃO FINAL**

```javascript
rangeDados.sort({ column: idxDataMovCO + 1, ascending: false });
// Ordena CONTAORDEM por DATA MOV. (mais novo → mais velho)
```

### **(7) AUDITORIA**

Relatório com:
- Total lido vs. elegível
- Sucessos vs. falhas
- Detalhe de cada match/erro
- Timestamps

---

## Mapeamento para Python

| JavaScript | Python | Finalidade |
|-----------|--------|-----------|
| `idxCO()`, `idxCT()` | `_get_index()` | Map header → índice |
| `removerAcentos()` | `_normalize_text()` | Remove acentos |
| `parseDataMov()` | `_parse_date()` | Parse de datas |
| `obterChaveDia()` | `_get_day_key()` | Chave dia YYYY-MM-DD |
| `seqState` | `seq_state` (dict) | Controle sequencial/dia |
| `ensureState()` | N/A (integrado em prepare) | Garante estado por dia |
| `gerarDescricaoComSequencialPorDia()` | `_generate_sequential_description()` | Gera N001, N002... |
| `dadosCO.forEach()` | `for idx, source_row in enumerate()` | Loop em linhas |
| `sheetCO.getRange().setValues()` | `batch_writer.batch_write_with_updates()` | Escreve em batch |
| Auditoria detalhada | `stats` dict | Log de processamento |

---

## Lógica-Chave: Sequencial Diário

```
seqState é GLOBAL durante toda execução.

Pré-processamento:
  1. Varrer CONTAORDEM existente
  2. Para cada linha com DESCRIÇÃO SOMA:
     - Split "BASE Nxxx"
     - Registrar em seqState[dia||base] que Nxxx foi usado
  
Processamento:
  Para cada linha elegível:
    - Encontrar match em CONSTANTES
    - Gerar próximo número: state.max + 1
    - Garantir que não foi usado (loop incrementa se necessário)
    - Gerar "BASE Nxxx"
    - Salvar novo max em state
    
Resultado:
  - Mesmo dia + mesma base: N001, N002, N003...
  - Dia diferente: reinicia em N001
  - Se re-rodar: continua numeração (N004, N005...)
```

---

## Critérios de Match (Ordem Importância)

1. **TEXTO** (obrigatório)
   - Normalizado (sem acentos)
   - Validação: `descCO_norm.includes(textoCT_norm)` OR vice-versa
   - Fuzzy matching (substring é suficiente)

2. **TIPO** (obrigatório)
   - Entrada = Entrada
   - Saída = Saída
   - Case-insensitive

3. **VALOR** (opcional)
   - Se CONSTANTES tem valor: diferença deve ser < 0,01
   - Se CONSTANTES não tem valor: ignorado (sempre OK)

**Todos os 3 devem passar para match suceder**

---

## Auditoria Completa

```
Início: dd/MM/yyyy HH:mm:ss

Processadas CO: N (total lido)
Elegíveis: N (DOC. SOMA vazio ou "EM ERRO")

Sucessos: N (encontrou match)
Falhas: N (não encontrou match ou erro)

Detalhes:
  [SUCESSO] MATCH CO[L123] -> CT[L45]
            ORIGEM: {desc | tipo | valor | data}
            DESTINO: {desc | tipo | valor}
            APLICADO: DOC.SOMA="..." DESCRIÇÃO SOMA="..."
            TIMESTAMP_CT="dd/MM/yyyy HH:mm:ss"
  
  [AVISO] SEM MATCH CO[L456]
          ORIGEM: {desc | tipo | valor | data}
          
  [INFO] Ordenação aplicada
```

---

## Implementação em Python (TransferMatchingService)

Segue a mesma lógica mas otimizada:

1. **Prepare Phase**: Todos dados em memória
2. **Matching Phase**: Match + sequencial durante prepare
3. **Batch Write Phase**: Uma única escrita em batch

Resultado: Mesma funcionalidade, 90% menos API calls!
