# Agenda Monteiro — Pipeline de Extração e Publicação

UI interativa para visualizar e revisar agenda de jogos e eventos escolares 2026.

## 🎯 Fluxo Rápido (3 passos)

### 1️⃣ Extrair dados dos PDFs (uma única vez)
```bash
# Instalar dependências Python
pip install --break-system-packages -r requirements.txt

# Extrair texto dos PDFs
python3 scripts/extract.py --input pdfs --output data/extracted.csv
```
**Resultado:** `data/extracted.csv` com 527 linhas brutes extraídas dos PDFs.

---

### 2️⃣ Revisar e corrigir dados manualmente
```bash
# Servir localmente
python3 -m http.server 8000 --directory .
# Abra: http://localhost:8000/review/
```

**Na UI de revisão:**
1. **Carregar CSV** → selecione `data/extracted.csv`
2. **Visualize** o snippet do PDF (esquerda)
3. **Corrija os campos** estruturados (direita):
   - Data, Dia, Período, Local, Hora, Quadra, Série, Esporte, Gênero, Times
4. **Navegue** com Anterior/Próximo
5. **Exporte CSV** revisado (botão verde)

Exemplo de linha corrigida:
```
04/05|Segunda|Manhã|Colégio Monteiro Lobato|8h00|Quadra Grande Externa|3º ano Ensino Médio|Basquete|Masc|VERMELHO X ROXO
```

---

### 3️⃣ Usar dados no app
```bash
# Copie o CSV revisado (baixado da UI)
cp ~/Downloads/extracted-reviewed-*.csv data/final.csv

# Converta para formato esperado pelo index.html
python3 scripts/convert_to_pipe.py --input data/final.csv --output data/rawData.txt
```

**Copie a saída** do script acima para o `const rawData = \`` no `index.html` raiz.

O `index.html` raiz será publicado automaticamente em GitHub Pages (`docs/` → GitHub Pages).

---

## 📁 Estrutura do Projeto

```
.
├── index.html               # 🎯 App principal (raiz) — publica em docs/
├── docs/
│   └── index.html          # Cópia para GitHub Pages
├── pdfs/                    # Entrada: PDFs dos jogos
├── data/
│   ├── extracted.csv       # Saída do extract.py (bruto, 527 linhas)
│   ├── final.csv           # Saída revisada da UI (depois do export)
│   └── rawData.txt         # Formato pipe-separado para index.html
├── scripts/
│   ├── extract.py          # Extrator de texto dos PDFs
│   ├── convert_to_pipe.py  # Converte CSV → formato pipe
│   └── parse.py            # Parser experimental (pode ignorar)
├── review/
│   ├── index.html          # 🎯 UI de revisão interativa
│   └── README.md           # Instruções detalhadas
└── requirements.txt         # Dependências Python
```

---

## 🔄 Fluxo Detalhado

### `extract.py` — Extração
- **Entrada:** PDFs em `pdfs/`
- **Processo:** Lê texto com `pdfplumber`; fallback OCR com `pytesseract` (opcional)
- **Saída:** `data/extracted.csv` com colunas: `pdf`, `page`, `line_no`, `raw`

### `review/index.html` — Revisão
- **Entrada:** `data/extracted.csv` (upload na UI)
- **Processo:** Visualiza snippet + corrija campos interativamente
- **Saída:** CSV revisado (download)

### `convert_to_pipe.py` — Conversão
- **Entrada:** CSV revisado (exportado da UI)
- **Processo:** Converte para formato pipe-separado
- **Saída:** Texto pronto para copiar/colar no `index.html`

---

## 📖 Formato de Dados

**Entrada (extracted.csv):**
```csv
pdf,page,line_no,raw
2026 GINCANA EFI-1º a 3º (1).pdf,1,7,DATA 04/05 Tarde 04/05 Tarde
TABELA OFICIAL DE JOGOS 2026 II.pdf,5,10,04/05|Segunda|Manhã|Colégio Monteiro Lobato|...
```

**Após revisão (final.csv):**
```csv
date,day,period,location,time,court,grade,sport,gender,teams,raw,pdf,page,line_no
04/05,Segunda,Manhã,Colégio Monteiro Lobato,8h00,Quadra Grande Externa,3º ano Ensino Médio,Basquete,Masc,VERMELHO X ROXO,...
```

**Formato final (rawData.txt):**
```
04/05|Segunda|Manhã|Colégio Monteiro Lobato|8h00|Quadra Grande Externa|3º ano Ensino Médio|Basquete|Masc|VERMELHO X ROXO
```

---

## 💡 Dicas de Uso

### Revisar dados rapidamente
- Use **Pular** para linhas incompletas ou OK
- Use **Anterior/Próximo** para editar
- **Salve frequentemente** (botão verde)

### Confirmar precisão
- Abra o PDF original lado-a-lado
- Valide campos críticos: Hora, Equipes, Série

### Publicar no GitHub Pages
1. Copie `index.html` (atualizado) para `docs/index.html`
2. Faça commit + push
3. Ative GitHub Pages nas settings do repo (branch: `main`, pasta: `docs/`)
4. Acesse: `https://seu-usuario.github.io/jogos-monteiro/`

---

## 🛠️ Troubleshooting

| Erro | Solução |
|------|---------|
| `ModuleNotFoundError: pdfplumber` | `pip install --break-system-packages -r requirements.txt` |
| Tesseract não encontrado (OCR) | `sudo apt-get install tesseract-ocr` (Linux) ou `brew install tesseract` (Mac) |
| Arquivo extraído vazio | Verifique se PDFs estão em `pdfs/` |
| UI não carrega dados | Verifique formato do CSV (colunas: `pdf,page,line_no,raw`) |

---

## 📚 Referências
- [pdfplumber docs](https://github.com/jsvine/pdfplumber)
- [pytesseract docs](https://pypi.org/project/pytesseract/)
- [GitHub Pages setup](https://docs.github.com/en/pages)
