#!/usr/bin/env python3
"""
Compara os dados estruturados do HTML (rawData) com o texto bruto extraído dos PDFs.

Uso:
  python3 scripts/compare.py

Saída:
  data/compare_report.html  — relatório visual interativo
  data/compare_report.txt   — relatório em texto puro
"""
import re
import os
import csv
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Lê o rawData do docs/index.html
# ---------------------------------------------------------------------------

def read_rawdata_from_html(html_path: str) -> list[dict]:
    """Extrai as linhas pipe-separated de `const rawData = \`...\``"""
    with open(html_path, encoding='utf-8') as f:
        content = f.read()

    m = re.search(r'const rawData\s*=\s*`(.*?)`', content, re.DOTALL)
    if not m:
        raise ValueError("rawData não encontrado no HTML!")

    lines = [l.strip() for l in m.group(1).splitlines() if l.strip()]
    games = []
    for line in lines:
        parts = [p.strip() for p in line.split('|')]
        if len(parts) == 10:
            games.append({
                'date': parts[0], 'day': parts[1], 'period': parts[2],
                'location': parts[3], 'time': parts[4], 'court': parts[5],
                'grade': parts[6], 'sport': parts[7], 'gender': parts[8],
                'teams': parts[9],
                'raw_line': line
            })
    return games

# ---------------------------------------------------------------------------
# 2. Lê o CSV extraído dos PDFs
# ---------------------------------------------------------------------------

def read_extracted_csv(csv_path: str) -> list[dict]:
    rows = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows

# ---------------------------------------------------------------------------
# 3. Helpers
# ---------------------------------------------------------------------------

def normalize(s: str) -> str:
    """Remove acentos, lowercase, espaço normalizado."""
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s).strip().lower()

def parse_time_to_minutes(t: str) -> int:
    t = t.split('/')[0].strip()
    m = re.match(r'(\d+)[hH](\d*)', t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2) or 0)
    return 9999

# ---------------------------------------------------------------------------
# 4. Para cada linha bruta do CSV, tenta achar a linha do HTML correspondente
# ---------------------------------------------------------------------------

# Patterns para extrair campos das linhas brutas
DATE_PAT    = re.compile(r'\b(\d{2}/\d{2})\b')
TIME_PAT    = re.compile(r'\b(\d{1,2}h\d{0,2})\b', re.IGNORECASE)
SPORT_MAP   = {
    'basquete': ['basquete', 'basquetebol'],
    'voleibol': ['voleibol', 'volei', 'vôlei', 'newcomb', 'bola por cima'],
    'futsal': ['futsal'],
    'futebol': ['futebol 7', 'futebol'],
    'handebol': ['handebol'],
    'corrida': ['corrida'],
    'salto': ['salto'],
    'dodgeball': ['dodgeball'],
    'queimada': ['queimada'],
    'gincana': ['gincana', 'desafio', 'circuito'],
}
TEAM_COLORS = ['vermelho', 'roxo', 'verde', 'azul', 'amarelo']

def find_teams_in_line(text: str) -> str | None:
    n = normalize(text)
    found = [c.upper() for c in TEAM_COLORS if c in n]
    if 'p-' in n or ' p ' in n:
        found.append('P-')
    if 'v-' in n:
        found.append('V-')
    if len(found) >= 2:
        return f"{found[0]} X {found[1]}"
    return None

def extract_date(text: str) -> str | None:
    m = DATE_PAT.search(text)
    return m.group(1) if m else None

def extract_time(text: str) -> str | None:
    m = TIME_PAT.search(text)
    if m:
        raw = m.group(1).lower()
        # Normaliza: "8h" → "8h00", "8h0" → "8h00"
        if re.match(r'^\d{1,2}h$', raw):
            raw += '00'
        elif re.match(r'^\d{1,2}h\d$', raw):
            raw += '0'
        return raw
    return None

def detect_sport(text: str) -> str | None:
    n = normalize(text)
    for sport, keywords in SPORT_MAP.items():
        for kw in keywords:
            if kw in n:
                return sport
    return None

# ---------------------------------------------------------------------------
# 5. Analisa cobertura: para cada jogo do HTML, verifica se aparece no PDF
# ---------------------------------------------------------------------------

def build_pdf_index(extracted_rows: list[dict]) -> dict:
    """Indexa linhas brutas por (pdf, data) para busca rápida."""
    idx: dict = {}
    for row in extracted_rows:
        date = extract_date(row['raw'])
        if date:
            key = (row['pdf'], date)
            if key not in idx:
                idx[key] = []
            idx[key].append(row)
    return idx

def find_evidence_in_pdf(game: dict, pdf_index: dict) -> list[str]:
    """Retorna as linhas brutas do PDF que corroboram este jogo."""
    sport = normalize(game['sport'])
    time_norm = normalize(game['time'].split('/')[0])
    date = game['date']

    candidates = []
    for key, rows in pdf_index.items():
        if key[1] != date:
            continue
        for row in rows:
            n = normalize(row['raw'])
            # Precisa ter pelo menos horário ou esporte coincidindo
            time_in_row = extract_time(row['raw'])
            has_time = time_in_row and normalize(time_in_row) == time_norm
            has_sport = any(kw in n for kw in [sport] + SPORT_MAP.get(sport, []))
            if has_time or has_sport:
                candidates.append(row['raw'])

    return candidates[:5]  # max 5 evidências por jogo

# ---------------------------------------------------------------------------
# 6. Verifica integridade dos dados do HTML
# ---------------------------------------------------------------------------

def check_html_data_issues(games: list[dict]) -> list[dict]:
    """Detecta problemas nos dados do HTML."""
    issues = []
    seen_keys = {}

    for i, g in enumerate(games):
        problems = []

        # Duplicata
        key = (g['date'], g['time'], g['court'], g['location'])
        if key in seen_keys:
            problems.append(f"DUPLICATA com linha {seen_keys[key]+1}")
        seen_keys[key] = i

        # Campos vazios
        for field in ['date', 'time', 'location', 'court', 'grade', 'sport']:
            if not g[field] or g[field] == '-':
                problems.append(f"Campo '{field}' vazio")

        # Data fora do intervalo esperado (04/05 a 07/05)
        if g['date'] and not re.match(r'0[4-7]/05', g['date']):
            problems.append(f"Data fora do intervalo: {g['date']}")

        # Horário inválido
        if not re.match(r'\d{1,2}h\d{0,2}', g['time']):
            problems.append(f"Horário inválido: {g['time']}")

        if problems:
            issues.append({'line': i+1, 'game': g, 'problems': problems})

    return issues

# ---------------------------------------------------------------------------
# 7. Gera relatório HTML
# ---------------------------------------------------------------------------

REPORT_HTML_TMPL = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Relatório de Comparação — Jogos 2026</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
  .card {{ @apply bg-white rounded-xl shadow-sm border p-4 mb-3; }}
  pre {{ white-space: pre-wrap; word-break: break-all; font-size: 0.75rem; }}
  .ok {{ background: #f0fdf4; border-left: 4px solid #22c55e; }}
  .warn {{ background: #fff7ed; border-left: 4px solid #f97316; }}
  .error {{ background: #fef2f2; border-left: 4px solid #ef4444; }}
  .info {{ background: #eff6ff; border-left: 4px solid #3b82f6; }}
  .tab-btn.active {{ background:#1e40af; color:white; }}
  .tab-content {{ display:none; }}
  .tab-content.active {{ display:block; }}
</style>
</head>
<body class="bg-gray-100 p-4">
<div class="max-w-6xl mx-auto">

<div class="bg-gradient-to-r from-blue-900 to-indigo-800 text-white rounded-2xl p-6 mb-6 shadow-xl">
  <h1 class="text-2xl font-black mb-1">📊 Relatório de Comparação de Dados</h1>
  <p class="text-blue-200 text-sm">HTML (rawData) ↔ PDFs extraídos</p>
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
    <div class="bg-white/10 rounded-xl p-3 text-center">
      <div class="text-2xl font-black">{total_html}</div>
      <div class="text-xs text-blue-200">Jogos no HTML</div>
    </div>
    <div class="bg-white/10 rounded-xl p-3 text-center">
      <div class="text-2xl font-black">{total_pdf_lines}</div>
      <div class="text-xs text-blue-200">Linhas extraídas (PDFs)</div>
    </div>
    <div class="bg-white/10 rounded-xl p-3 text-center">
      <div class="text-2xl font-black text-{issues_color}">{total_issues}</div>
      <div class="text-xs text-blue-200">Problemas detectados</div>
    </div>
    <div class="bg-white/10 rounded-xl p-3 text-center">
      <div class="text-2xl font-black text-{orphans_color}">{total_orphans}</div>
      <div class="text-xs text-blue-200">Linhas PDF sem match</div>
    </div>
  </div>
</div>

<!-- TABS -->
<div class="flex gap-2 mb-4 flex-wrap">
  <button class="tab-btn active px-4 py-2 rounded-lg font-bold text-sm bg-white border border-slate-200 hover:border-blue-400" onclick="showTab('issues')">⚠️ Problemas no HTML ({total_issues})</button>
  <button class="tab-btn px-4 py-2 rounded-lg font-bold text-sm bg-white border border-slate-200 hover:border-blue-400" onclick="showTab('orphans')">🔍 Linhas PDF sem match ({total_orphans})</button>
  <button class="tab-btn px-4 py-2 rounded-lg font-bold text-sm bg-white border border-slate-200 hover:border-blue-400" onclick="showTab('coverage')">✅ Cobertura por data</button>
  <button class="tab-btn px-4 py-2 rounded-lg font-bold text-sm bg-white border border-slate-200 hover:border-blue-400" onclick="showTab('rawpdf')">📄 PDF bruto por arquivo</button>
</div>

<!-- TAB: Problemas -->
<div id="tab-issues" class="tab-content active">
  <h2 class="text-lg font-black text-slate-800 mb-4">⚠️ Problemas detectados no HTML</h2>
  {issues_html}
</div>

<!-- TAB: Orphans -->
<div id="tab-orphans" class="tab-content">
  <h2 class="text-lg font-black text-slate-800 mb-4">🔍 Linhas extraídas dos PDFs que não matcheiam com nenhum jogo do HTML</h2>
  <p class="text-sm text-slate-500 mb-4">Estas linhas podem indicar jogos ausentes no HTML ou são cabeçalhos/rodapés dos PDFs.</p>
  {orphans_html}
</div>

<!-- TAB: Cobertura -->
<div id="tab-coverage" class="tab-content">
  <h2 class="text-lg font-black text-slate-800 mb-4">✅ Cobertura por data e arquivo PDF</h2>
  {coverage_html}
</div>

<!-- TAB: PDF bruto -->
<div id="tab-rawpdf" class="tab-content">
  <h2 class="text-lg font-black text-slate-800 mb-4">📄 Texto bruto extraído por arquivo PDF</h2>
  {rawpdf_html}
</div>

</div>
<script>
function showTab(name) {{
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
}}
</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# 8. Main
# ---------------------------------------------------------------------------

def main():
    base = Path(__file__).parent.parent
    html_path = base / 'docs/index.html'
    csv_path  = base / 'data/extracted.csv'
    out_html  = base / 'data/compare_report.html'
    out_txt   = base / 'data/compare_report.txt'

    print("Lendo HTML...")
    games = read_rawdata_from_html(str(html_path))
    print(f"  → {len(games)} jogos no HTML")

    print("Lendo CSV extraído...")
    extracted = read_extracted_csv(str(csv_path))
    print(f"  → {len(extracted)} linhas extraídas")

    # Índice de PDF por data
    pdf_index = build_pdf_index(extracted)

    # ---- Verifica problemas nos dados do HTML ----
    print("Verificando problemas no HTML...")
    issues = check_html_data_issues(games)
    print(f"  → {len(issues)} problemas")

    # ---- Para cada linha do PDF, verifica se algum jogo do HTML cobre ----
    print("Buscando linhas PDF sem correspondência no HTML...")
    html_dates = {g['date'] for g in games}
    html_times = {(g['date'], g['time'].split('/')[0]): g for g in games}

    orphan_rows = []
    # Filtra linhas que parecem ter dado, horário ou esporte mas não matcheiam
    game_signatures = set()
    for g in games:
        sig = (g['date'], normalize(g['time'].split('/')[0]), normalize(g['sport']))
        game_signatures.add(sig)

    for row in extracted:
        raw = row['raw']
        date = extract_date(raw)
        time = extract_time(raw)
        sport = detect_sport(raw)

        if not date or not time:
            continue  # Linhas sem data+horário não são jogos
        if date not in html_dates:
            continue  # Data completamente ausente do HTML → esperado para outros PDFs

        sig = (date, normalize(time), sport or '')
        if sport and sig not in game_signatures:
            orphan_rows.append(row)

    print(f"  → {len(orphan_rows)} linhas PDF candidatas a jogo sem match")

    # ---- Cobertura por data ----
    coverage: dict = {}
    for g in games:
        d = g['date']
        if d not in coverage:
            coverage[d] = {'html_count': 0, 'pdf_lines': []}
        coverage[d]['html_count'] += 1

    for row in extracted:
        date = extract_date(row['raw'])
        if date and date in coverage:
            coverage[date]['pdf_lines'].append(row['raw'])

    # ---- Agrupamento por PDF ----
    pdfs: dict = {}
    for row in extracted:
        p = row['pdf']
        if p not in pdfs:
            pdfs[p] = []
        pdfs[p].append(row)

    # ---- Gera HTML ----
    def esc(s):
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Issues HTML
    issues_html = ''
    if not issues:
        issues_html = '<div class="ok p-4 rounded-xl"><strong>✅ Nenhum problema encontrado nos dados do HTML!</strong></div>'
    else:
        for iss in issues:
            g = iss['game']
            issues_html += f'''
<div class="error p-4 rounded-xl mb-3">
  <div class="font-black text-red-700 mb-1">Linha {iss["line"]}: {esc(g["date"])} | {esc(g["time"])} | {esc(g["location"])} | {esc(g["sport"])}</div>
  <ul class="list-disc pl-5 text-sm text-red-600">
    {''.join(f'<li>{esc(p)}</li>' for p in iss["problems"])}
  </ul>
  <pre class="mt-2 text-xs text-slate-500 bg-slate-50 p-2 rounded">{esc(g["raw_line"])}</pre>
</div>'''

    # Orphans HTML
    orphans_html = ''
    if not orphan_rows:
        orphans_html = '<div class="ok p-4 rounded-xl"><strong>✅ Todas as linhas com conteúdo de jogo têm correspondência no HTML!</strong></div>'
    else:
        # Agrupa por PDF
        orphans_by_pdf: dict = {}
        for row in orphan_rows:
            p = row['pdf']
            if p not in orphans_by_pdf:
                orphans_by_pdf[p] = []
            orphans_by_pdf[p].append(row)

        for pdf_name, rows in orphans_by_pdf.items():
            orphans_html += f'<h3 class="font-black text-slate-700 mt-4 mb-2">📄 {esc(pdf_name)} ({len(rows)} linhas)</h3>'
            for row in rows:
                orphans_html += f'''
<div class="warn p-3 rounded-xl mb-2 text-sm">
  <span class="text-xs font-bold text-orange-500">Pág {esc(row["page"])} • Linha {esc(row["line_no"])}</span>
  <pre class="mt-1 text-slate-700">{esc(row["raw"])}</pre>
</div>'''

    # Coverage HTML
    coverage_html = '<div class="grid grid-cols-1 md:grid-cols-2 gap-4">'
    for date in sorted(coverage.keys()):
        cov = coverage[date]
        pdf_count = len(cov['pdf_lines'])
        color = 'ok' if pdf_count > 0 else 'warn'
        coverage_html += f'''
<div class="{color} p-4 rounded-xl">
  <div class="font-black text-slate-800 mb-1">📅 {esc(date)}</div>
  <div class="text-sm">Jogos no HTML: <strong>{cov["html_count"]}</strong></div>
  <div class="text-sm">Linhas no PDF com esta data: <strong>{pdf_count}</strong></div>
  <details class="mt-2">
    <summary class="text-xs cursor-pointer text-slate-500 hover:text-slate-700">Ver linhas PDF ({pdf_count})</summary>
    <div class="mt-2 space-y-1 max-h-48 overflow-y-auto">
      {''.join(f'<pre class="text-xs bg-white p-1 rounded border">{esc(l)}</pre>' for l in cov['pdf_lines'][:30])}
      {'<div class="text-xs text-slate-400">... e mais</div>' if pdf_count > 30 else ''}
    </div>
  </details>
</div>'''
    coverage_html += '</div>'

    # Raw PDF HTML
    rawpdf_html = ''
    for pdf_name, rows in pdfs.items():
        rawpdf_html += f'<h3 class="font-black text-slate-700 mt-4 mb-2">📄 {esc(pdf_name)} ({len(rows)} linhas)</h3>'
        rawpdf_html += '<div class="bg-white rounded-xl border p-4 font-mono text-xs overflow-auto max-h-96">'
        for row in rows:
            raw = row['raw']
            # Highlight datas, horários e nomes de times
            raw_esc = esc(raw)
            for pat, color in [
                (r'\b\d{2}/\d{2}\b', 'text-blue-600 font-bold'),
                (r'\b\d{1,2}h\d{0,2}\b', 'text-emerald-600 font-bold'),
            ]:
                raw_esc = re.sub(pat, lambda m: f'<span class="{color}">{m.group()}</span>', raw_esc)
            for team in ['VERMELHO', 'ROXO', 'VERDE', 'AZUL']:
                colors = {'VERMELHO': 'bg-red-100 text-red-700', 'ROXO': 'bg-purple-100 text-purple-700', 'VERDE': 'bg-green-100 text-green-700', 'AZUL': 'bg-blue-100 text-blue-700'}
                raw_esc = raw_esc.replace(team, f'<span class="px-1 rounded {colors[team]}">{team}</span>')
            rawpdf_html += f'<div class="py-0.5 hover:bg-slate-50 px-1 rounded border-b border-slate-50"><span class="text-slate-300 select-none mr-2">{esc(row["page"])}.{esc(row["line_no"])}</span>{raw_esc}</div>'
        rawpdf_html += '</div>'

    report = REPORT_HTML_TMPL.format(
        total_html=len(games),
        total_pdf_lines=len(extracted),
        total_issues=len(issues),
        issues_color='red-300' if issues else 'green-300',
        total_orphans=len(orphan_rows),
        orphans_color='orange-300' if orphan_rows else 'green-300',
        issues_html=issues_html,
        orphans_html=orphans_html,
        coverage_html=coverage_html,
        rawpdf_html=rawpdf_html,
    )

    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n✅ Relatório HTML: {out_html}")

    # Texto simples
    lines = [
        "=" * 70,
        "RELATÓRIO DE COMPARAÇÃO — JOGOS 2026",
        "=" * 70,
        f"Jogos no HTML:         {len(games)}",
        f"Linhas extraídas PDF:  {len(extracted)}",
        f"Problemas no HTML:     {len(issues)}",
        f"Linhas PDF sem match:  {len(orphan_rows)}",
        "",
    ]
    if issues:
        lines.append("--- PROBLEMAS NO HTML ---")
        for iss in issues:
            g = iss['game']
            lines.append(f"  Linha {iss['line']}: {g['date']} {g['time']} {g['location']} {g['sport']}")
            for p in iss['problems']:
                lines.append(f"    • {p}")
        lines.append("")
    if orphan_rows:
        lines.append("--- LINHAS PDF SEM MATCH ---")
        for row in orphan_rows[:50]:
            lines.append(f"  [{row['pdf']} p{row['page']}] {row['raw']}")
        if len(orphan_rows) > 50:
            lines.append(f"  ... e mais {len(orphan_rows)-50} linhas")

    with open(out_txt, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"✅ Relatório texto: {out_txt}")

    return len(issues), len(orphan_rows)

if __name__ == '__main__':
    issues, orphans = main()
    print(f"\nResumo: {issues} problemas no HTML, {orphans} linhas PDF sem match")
