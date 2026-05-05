# Pipeline de Extração e Verificação de PDFs

## 🎯 Fluxo Rápido

### 1️⃣ Extrair dados dos PDFs (Uma vez)
```bash
pip install --break-system-packages -r requirements.txt
python3 scripts/extract.py --input pdfs --output data/extracted.csv
```
Resultado: `data/extracted.csv` com linhas brutas dos PDFs.

---

### 2️⃣ Revisar e corrigir manualmente
```bash
# Servir localmente
python3 -m http.server 8000 --directory .
# Acesse: http://localhost:8000/review/
```

**Na UI de revisão:**
1. Clique **"Carregar CSV"** → selecione `data/extracted.csv`
2. Visualize o **snippet do PDF** (esquerda) e **corrija os campos** (direita):
   - **Data** (DD/MM) — ex: 04/05
   - **Dia** (Segunda, Terça, etc.)
   - **Período** (Manhã, Tarde, Noite)
   - **Local** — ex: Colégio Monteiro Lobato
   - **Hora** — ex: 8h00
   - **Quadra** — ex: Quadra Grande Externa
   - **Série** — ex: 3º ano Ensino Médio
   - **Esporte** — ex: Basquete
   - **Gênero** (Masc, Fem, Misto)
   - **Times** — ex: VERMELHO X ROXO

3. Use **Anterior/Próximo** para navegar ou **Pular** para linhas sem dados
4. Clique **Exportar CSV** para baixar o arquivo revisado

---

### 3️⃣ Usar os dados no app principal
```bash
# Copie o CSV revisado para a raiz
cp data/extracted-reviewed-YYYY-MM-DD.csv data/final.csv

# Converta para JSON (opcional)
python3 scripts/csv_to_json.py --input data/final.csv --output data/games.json

# Atualize index.html com os dados
# (instruções abaixo)
```

---

## 📋 Formato Esperado

Cada linha do CSV revisado deve ter:
```
data,dia,período,local,hora,quadra,série,esporte,gênero,times,raw,pdf,page,line_no
04/05,Segunda,Manhã,Colégio Monteiro Lobato,8h00,Quadra Grande Externa,3º ano Ensino Médio,Basquete,Masc,VERMELHO X ROXO,<raw original>,<pdf>,<page>,<line>
```

---

## 🎮 Integrar com `index.html` raiz

Após revisar, copie os dados para o `index.html`:

```javascript
// No index.html, substitua rawData por:
const rawData = `
04/05|Segunda|Manhã|Colégio Monteiro Lobato|8h00|Quadra Grande Externa|3º ano Ensino Médio|Basquete|Masc|VERMELHO X ROXO
04/05|Segunda|Manhã|Colégio Monteiro Lobato|8h00|Quadra Pequena Externa|6º ano Ensino Fundamental II|Basquetebol|Masc|VERMELHO X ROXO
...
`;
```

Ou use JSON:
```javascript
const gamesData = [
  { date: "04/05", day: "Segunda", period: "Manhã", ... },
  { date: "04/05", day: "Segunda", period: "Manhã", ... }
];
```

---

## 📚 Arquivos Principais

- `scripts/extract.py` — extrator de texto dos PDFs
- `scripts/csv_to_json.py` — converte CSV → JSON
- `review/index.html` — UI de revisão interativa
- `data/extracted.csv` — saída da extração (bruta)
- `data/final.csv` — saída revisada (limpa)
