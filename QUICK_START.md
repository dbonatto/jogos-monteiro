# 🚀 Quick Start — Agenda Monteiro

## 3 Passos para Publicar a Agenda

### 1️⃣ Extrair (5 min)
```bash
pip install --break-system-packages -r requirements.txt
python3 scripts/extract.py --input pdfs --output data/extracted.csv
```
✅ Gera `data/extracted.csv` (527 linhas brutes)

---

### 2️⃣ Revisar (30-60 min)
```bash
python3 -m http.server 8000 --directory .
# Abra: http://localhost:8000/review/
```

**Na UI:**
- Upload `data/extracted.csv`
- Corrija cada jogo (data|dia|período|local|hora|quadra|série|esporte|gênero|times)
- Export CSV revisado

✅ Gera CSV corrigido (download na UI)

---

### 3️⃣ Publicar (5 min)
```bash
# Converta CSV revisado para formato pipe
python3 scripts/convert_to_pipe.py --input ~/Downloads/extracted-reviewed-*.csv --output data/rawData.txt

# Copie a saída do comando acima para o const rawData no index.html
# Depois: commit + push → GitHub Pages

# Ou para servir localmente:
python3 -m http.server 8000 --directory .
# Abra: http://localhost:8000/
```

✅ Publicado! 🎉

---

## Arquivos Principais

| Arquivo | Propósito |
|---------|-----------|
| `index.html` | App principal (raiz) — publica em `docs/` |
| `review/index.html` | UI para revisar dados |
| `scripts/extract.py` | Extrai texto dos PDFs |
| `scripts/convert_to_pipe.py` | Converte CSV → formato do app |
| `data/extracted.csv` | Saída bruta da extração |

---

## Formato Esperado

Cada linha deve ter este formato:
```
data|dia|período|local|hora|quadra|série|esporte|gênero|times
04/05|Segunda|Manhã|Colégio Monteiro Lobato|8h00|Quadra Grande Externa|3º ano Ensino Médio|Basquete|Masc|VERMELHO X ROXO
```

---

## Dúvidas?

📖 Veja `README.md` para documentação completa  
🛠️ Veja `review/README.md` para instruções detalhadas de revisão
