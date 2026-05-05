#!/usr/bin/env python3
"""extract_v2.py — Reliable table-based extractor for Jogos Monteiro 2026 PDFs.

Uses pdfplumber's extract_tables() (not raw text) to correctly read the
multi-column schedule grid, avoiding the column-collapse problem of the
old text-based extractor.

Handles:
  - 4-court CML pages (Manhã / Tarde / Noite)
  - 3-court Monteiro Open pages
  - PUCRS athletics pages (multi-grade cells → expanded to one record each)
  - Futebol 7 pages (multi-grade cells)
  - p13 overflow artifact (skipped with warning)
  - "QUA|DRA GRANDE" pipe artifact in court names

Workflow:
  1. python3 scripts/extract_v2.py --diag       # inspect every page (no output)
  2. python3 scripts/extract_v2.py               # extract → data/games_from_pdf.csv
  3. python3 scripts/extract_v2.py --audit       # diff extracted vs docs/data/games.csv

Output:
  data/games_from_pdf.csv    — pipe-separated, same format as docs/data/games.csv
  data/extraction_errors.txt — warnings for cells that could not be fully parsed
"""

import os, re, sys, argparse, unicodedata
from pathlib import Path
import pdfplumber

# ── Paths ──────────────────────────────────────────────────────────────────────
PDF_DIR     = Path("pdfs")
MAIN_PDF    = "TABELA OFICIAL DE JOGOS 2026 II.pdf"
OUTPUT_CSV  = Path("data/games_from_pdf.csv")
ERRORS_FILE = Path("data/extraction_errors.txt")
REFERENCE   = Path("docs/data/games.csv")

FIELD_ORDER = ("date", "day", "period", "location", "time", "court",
               "grade", "sport", "gender", "teams")

# ── Normalization tables ───────────────────────────────────────────────────────

# Canonical location names (keys are ASCII-lowercased for lookup)
LOCATION_CANON = {
    "colegio monteiro lobato":      "Colégio Monteiro Lobato",
    "colegio monteiro":             "Colégio Monteiro Lobato",   # partial match
    "monteiro open":                "Monteiro Open",
    "estadio da pucrs":             "Estádio da PUCRS",
    "estadio pucrs":                "Estádio da PUCRS",
    "campos de futebol 7":          "Campos de Futebol 7 - PUCRS",
    "campos de futebol 7 - pucrs":  "Campos de Futebol 7 - PUCRS",
}

# Canonical court names (keys are ASCII-lowercased for lookup)
COURT_CANON = {
    "quadra grande externa":        "Quadra Grande Externa",
    "quadra pequena externa":       "Quadra Pequena Externa",
    "quadra coberta":               "Quadra Coberta",
    "quadra de voleibol externa":   "Quadra de Voleibol Externa",
    "quadra de voleibol":           "Quadra de Voleibol",
    "grama grande":                 "Grama Grande",
    "quadra 1 e 2":                 "Quadra 1 e 2",
    "quadra 1":                     "Quadra 1",
    "quadra 2":                     "Quadra 2",
    "quadra grande":                "Quadra Grande",
    "quadra pequena":               "Quadra Pequena",
    "quadra voleibol":              "Quadra Voleibol",
    "quadra sintetica":             "Quadra Sintética",
    "sala 101":                     "Sala 101",
    "campo de futebol 11":          "Campo de Futebol 11",
    "caixa de areia":               "Caixa de Areia",
    "colchao de saltos estadio":    "Colchão de Saltos Estádio",
    "colchao de saltos indoor":     "Colchão de Saltos Indoor",
    "pista de corrida":             "Pista de Corrida",
    "quadra a de futebol 7":        "Quadra A de Futebol 7",
    "quadra b de futebol 7":        "Quadra B de Futebol 7",
    "quadrinha de volei":           "Quadrinha de Vôlei",
    "quadras de areia":             "Quadras de Areia",
    "area em frente ao teatro":     "Área em frente ao teatro",
}

# Sport normalization: map ASCII-lowercased PDF spellings → canonical CSV names
SPORT_CANON = {
    "basquete":                 "Basquete",
    "basquetebol":              "Basquetebol",
    "futsal":                   "Futsal",
    "futebol de campo":         "Futebol",       # PUCRS uses this phrase
    "futebol 7":                "Futebol 7",
    "futebol":                  "Futebol",
    "voleibol":                 "Voleibol",
    "volei":                    "Vôlei",          # no-accent variant
    "voley":                    "Vôlei",
    "handebol":                 "Handebol",
    "queimada dos numeros":     "Queimada dos Números",
    "queimada":                 "Queimada",
    "dodgeball":                "Dodgeball",
    "newcomb":                  "Newcomb",
    "bola por cima da rede":    "Bola Por Cima da Rede",
    "bola por cima":            "Bola Por Cima da Rede",
    "corrida":                  "Corrida",
    "salto em distancia":       "Salto em Distância",
    "salto em altura":          "Salto em Altura",
    "gincana":                  "Gincana",
    "desafio academico":        "Desafio Acadêmico",
    "circuito":                 "Circuito",
}

DAY_CANON = {
    "segunda": "Segunda",
    "terca":   "Terça",
    "quarta":  "Quarta",
    "quinta":  "Quinta",
    "sexta":   "Sexta",
    "sabado":  "Sábado",
}

_ORD = {1:"1º", 2:"2º", 3:"3º", 4:"4º", 5:"5º",
        6:"6º", 7:"7º", 8:"8º", 9:"9º"}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _asc(s: str) -> str:
    """ASCII-lowercased string — used ONLY for lookup/matching, never for output."""
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()


def derive_period(time_str: str) -> str | None:
    m = re.match(r"(\d{1,2})h", time_str or "")
    if not m:
        return None
    h = int(m.group(1))
    return "Manhã" if h < 13 else "Tarde" if h < 18 else "Noite"


def normalize_time(raw: str) -> str | None:
    """'8h' → '8h00', '8h40' stays, '10:30' → '10h30'."""
    raw = (raw or "").strip()
    m = re.match(r"(\d{1,2})\s*[hH:]\s*(\d{2})?", raw)
    if m:
        return f"{int(m.group(1))}h{m.group(2) or '00'}"
    return None


def normalize_location(text: str) -> str | None:
    key = _asc(text)
    # Exact match first
    if key in LOCATION_CANON:
        return LOCATION_CANON[key]
    # Substring match
    for k, v in LOCATION_CANON.items():
        if k in key:
            return v
    return None


def normalize_court(header_cell: str) -> str:
    """Extract canonical court name from a table header cell."""
    if not header_cell:
        return ""
    # Remove PDF table-line artifacts (pipe chars split words like "QUA|DRA")
    cleaned = header_cell.replace("|", "").replace("\u2502", "")
    lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
    if not lines:
        return ""

    first = lines[0].strip()
    # Remove trailing colon (e.g. "QUADRA 1:")
    first = re.sub(r"\s*:$", "", first).strip()
    # Collapse multiple spaces from pipe removal
    first = re.sub(r"\s{2,}", " ", first).strip()

    key = _asc(first)

    # Special case: "COLCHÃO DE SALTOS" needs a second line to disambiguate
    if key == "colchao de saltos" and len(lines) > 1:
        sec = _asc(lines[1])
        if "estadio" in sec or "estadio" in sec:
            return "Colchão de Saltos Estádio"
        if "indoor" in sec:
            return "Colchão de Saltos Indoor"

    if key in COURT_CANON:
        return COURT_CANON[key]

    # Fallback: return the cleaned first-line text with proper casing
    # (will surface in audit for manual review)
    return first.title()


def normalize_sport(text: str) -> str | None:
    """Find the sport keyword in a cell and return its canonical name."""
    key = _asc(text)
    # Try longer keys first to avoid "futebol" matching before "futebol 7"
    for k in sorted(SPORT_CANON, key=len, reverse=True):
        if k in key:
            return SPORT_CANON[k]
    return None


def normalize_gender(text: str) -> str | None:
    u = text.upper()
    if re.search(r"FEMININ[OA]\b", u) or re.search(r"\bFEM\b", u):
        return "Fem"
    if re.search(r"MASCULIN[OA]\b|MASCULIM|\bMASC\b", u):
        return "Masc"
    if "MISTO" in u:
        return "Misto"
    return None


def parse_grades(text: str, page_header: str = "") -> tuple[list[str], list[str]]:
    """
    Extract ALL grade numbers from cell text. Returns (grades, errors).

    Disambiguation rules:
      6-9                          → always Ensino Fundamental II
      4-5                          → always Ensino Fundamental I
      1-3 + EM in cell             → Ensino Médio
      1-3 + EFI in cell            → Ensino Fundamental I
      1-3 + EM in page header      → Ensino Médio
        (e.g. "ENSINO FUNDAMENTAL II E ENSINO MÉDIO" page title)
      1-3 alone, no header signal  → error (ambiguous)

    Multi-grade cells like "9º e 8º ano" produce multiple entries.
    Turma suffix is attached when present (for single-grade cells only).
    """
    t = _asc(text)
    is_em  = bool(re.search(r"\bem\b|ensino.?medio", t))
    is_efi = bool(re.search(r"ef.?i\b|ensino.?fundamental.?i\b", t))
    # Page header may say "ENSINO FUNDAMENTAL II E ENSINO MÉDIO";
    # when EM appears in the header, ambiguous grades 1-3 resolve to EM because
    # EFI cells in such pages always carry an explicit 'EF I' / 'EFI' qualifier.
    header_implies_em = bool(re.search(r"ensino.?medio|\bem\b", _asc(page_header)))

    nums = [int(m.group(1)) for m in re.finditer(r"(\d)[oOºª°]", text)]
    if not nums:
        return [], [f"no grade number found in: {text!r}"]

    # Turma suffix only makes sense for single-grade cells
    turma_m = re.search(r"turma\s*(\d+)", text, re.IGNORECASE)
    turma   = f" (Turma {turma_m.group(1)})" if turma_m and len(nums) == 1 else ""

    grades = []
    errors = []
    for n in nums:
        if n in (6, 7, 8, 9):
            grades.append(f"{_ORD[n]} ano Ensino Fundamental II{turma}")
        elif n in (4, 5):
            grades.append(f"{_ORD[n]} ano Ensino Fundamental I{turma}")
        elif n in (1, 2, 3):
            if is_em or (not is_efi and header_implies_em):
                grades.append(f"{_ORD[n]} ano Ensino Médio")
            elif is_efi:
                grades.append(f"{_ORD[n]} ano Ensino Fundamental I{turma}")
            else:
                errors.append(
                    f"ambiguous grade {n}º (no EM/EFI qualifier) in: {text!r}"
                )
        else:
            errors.append(f"unexpected grade number {n} in: {text!r}")

    return grades, errors


def normalize_teams(text: str) -> str | None:
    """Find 'TEAM x TEAM' line and return normalized 'TEAM X TEAM' form."""
    for line in text.splitlines():
        line = line.strip()
        # Must contain a standalone x AND have at least one uppercase letter
        if re.search(r"\bx\b", line, re.IGNORECASE) and re.search(r"[A-Z]", line):
            # Uppercase X, clean placeholder dashes, collapse whitespace
            result = re.sub(r"\s+[xX]\s+", " X ", line).upper()
            result = re.sub(r"(P|V)-[_\s]*", r"\1-", result)
            result = re.sub(r"\s+", " ", result).strip()
            return result
    return None

# ── Page header parser ─────────────────────────────────────────────────────────

def parse_page_header(page_text: str) -> dict:
    """
    Extract date, day, location from the text above the table.
    Returns a dict; missing fields are absent (not None).
    """
    result: dict = {}

    # Date: "07 DE MAIO DE 2026" or "7 DE MAIO 2026"
    m = re.search(r"(\d{1,2})\s+DE\s+MAIO\s+(?:DE\s+)?2026", page_text, re.IGNORECASE)
    if m:
        result["date"] = f"{int(m.group(1)):02d}/05"

    # Day of week
    m = re.search(
        r"(SEGUNDA|TERÇA|TERCA|QUARTA|QUINTA|SEXTA|SÁBADO|SABADO)(?:-FEIRA)?",
        page_text, re.IGNORECASE,
    )
    if m:
        result["day"] = DAY_CANON.get(_asc(m.group(1)), m.group(1).title())

    # Location: explicit "LOCAL: ..." line takes precedence
    m = re.search(r"LOCAL:\s*(.+?)(?:\n|$)", page_text, re.IGNORECASE)
    if m:
        loc = normalize_location(m.group(1).strip())
        if loc:
            result["location"] = loc
    if "location" not in result:
        # Fallback: search entire text
        loc = normalize_location(page_text)
        if loc:
            result["location"] = loc

    return result

# ── Game cell parser ───────────────────────────────────────────────────────────

_SKIP_CELL = re.compile(r"^(?:recreio|intervalo|apoio\s*geral?|[-_\s]+)$", re.IGNORECASE)


def parse_game_cell(cell_text: str, page_header: str = "") -> tuple[list[dict], list[str]]:
    """
    Parse one game cell.

    Returns (list_of_game_dicts, errors).
    Each game_dict has: grade, sport, gender, teams.

    Returns an empty list for empty/RECREIO cells.
    For multi-grade cells, returns one dict per grade (all sharing sport/gender/teams).
    """
    if not cell_text or not cell_text.strip():
        return [], []

    cell = cell_text.strip()

    # Check skip patterns on the first non-empty line
    first_line = next((l.strip() for l in cell.splitlines() if l.strip()), "")
    if _SKIP_CELL.match(first_line):
        return [], []

    errors: list[str] = []

    grades, grade_errors = parse_grades(cell, page_header=page_header)
    sport  = normalize_sport(cell)
    gender = normalize_gender(cell)
    teams  = normalize_teams(cell)

    errors.extend(grade_errors)
    if not sport:
        errors.append(f"sport not found in: {cell!r}")
    if not gender:
        errors.append(f"gender not found in: {cell!r}")
    if not teams:
        # Athletics events legitimately have no teams
        teams = "-"

    if not grades or not sport or not gender:
        return [], errors

    return [{"grade": g, "sport": sport, "gender": gender, "teams": teams}
            for g in grades], errors

# ── Main extractor ─────────────────────────────────────────────────────────────

def extract_pdf(pdf_path: Path, diag: bool = False) -> tuple[list[dict], list[str]]:
    games:  list[dict] = []
    errors: list[str]  = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text   = page.extract_text() or ""
            header = parse_page_header(text)

            # ── Validate header ────────────────────────────────────────────────
            if not header.get("date"):
                errors.append(f"p{page_num}: no date found — skipped (likely overflow/blank page)")
                if diag:
                    print(f"  p{page_num:02d}: ⚠  no date | text[:60]={text[:60]!r}")
                continue

            if not header.get("location"):
                errors.append(f"p{page_num}: no location found — skipped")
                if diag:
                    print(f"  p{page_num:02d}: ⚠  no location | text[:60]={text[:60]!r}")
                continue

            # ── Get table ──────────────────────────────────────────────────────
            tables = page.extract_tables()
            if not tables:
                errors.append(f"p{page_num}: no table found — skipped")
                if diag:
                    print(f"  p{page_num:02d}: ⚠  no table")
                continue

            table = tables[0]
            if len(table) < 2:
                errors.append(f"p{page_num}: table has only {len(table)} rows — skipped")
                continue

            # ── Parse court names from header row ──────────────────────────────
            header_row  = table[0]
            court_names = [normalize_court(header_row[c])
                           for c in range(1, len(header_row))]

            if diag:
                ncols = max(len(r) for r in table)
                print(f"  p{page_num:02d}: {header['date']} {header.get('day','?'):3s} "
                      f"{header.get('location','?')[:22]:22s} "
                      f"{len(table)}r×{ncols}c  {court_names}")

            # ── Parse game rows ────────────────────────────────────────────────
            for row in table[1:]:
                if not row or not row[0]:
                    continue

                time_norm = normalize_time(row[0])
                if not time_norm:
                    continue  # RECREIO or empty time cell

                period = derive_period(time_norm)

                for col_idx in range(1, len(row)):
                    ci    = col_idx - 1
                    court = court_names[ci] if ci < len(court_names) else ""

                    cell_games, cell_errors = parse_game_cell(row[col_idx], page_header=text)

                    ctx = (f"p{page_num} {header['date']} {header.get('day','')} "
                           f"{time_norm} [{court}]")

                    for e in cell_errors:
                        errors.append(f"{ctx}: {e}")

                    for g in cell_games:
                        games.append({
                            "date":     header["date"],
                            "day":      header.get("day", ""),
                            "period":   period,
                            "location": header["location"],
                            "time":     time_norm,
                            "court":    court,
                            "grade":    g["grade"],
                            "sport":    g["sport"],
                            "gender":   g["gender"],
                            "teams":    g["teams"],
                        })

    return games, errors

# ── CSV I/O ────────────────────────────────────────────────────────────────────

def write_csv(games: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for g in games:
            f.write("|".join(g[k] for k in FIELD_ORDER) + "\n")


def read_csv(path: Path) -> list[dict]:
    games = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("|")
            if len(parts) >= len(FIELD_ORDER):
                games.append(dict(zip(FIELD_ORDER, parts[:len(FIELD_ORDER)])))
    return games

# ── Audit ──────────────────────────────────────────────────────────────────────

def _slot_key(g: dict) -> tuple:
    """(date, location_asc, time, court_asc) — uniquely identifies a game slot."""
    return (g["date"], _asc(g["location"]), g["time"], _asc(g["court"]))


def _canon_sport(s: str) -> str:
    """Canonical sport for matching: strip accents, map known variants."""
    a = _asc(s)
    return _asc(SPORT_CANON.get(a, s))


def _game_match_key(g: dict) -> tuple:
    return (_slot_key(g), _asc(g["grade"]), _canon_sport(g["sport"]), g["gender"])


# Sources NOT covered by the main schedule PDF (expected "extra in CSV")
_EXPECTED_EXTRAS = {"Gincana", "Desafio Acadêmico", "Circuito", "Queimada dos Números"}


def run_audit(pdf_games: list[dict], csv_games: list[dict]) -> None:
    pdf_by_slot: dict = {}
    csv_by_slot: dict = {}
    for g in pdf_games:
        pdf_by_slot.setdefault(_slot_key(g), []).append(g)
    for g in csv_games:
        csv_by_slot.setdefault(_slot_key(g), []).append(g)

    all_slots = sorted(set(pdf_by_slot) | set(csv_by_slot))

    missing_from_csv: list[dict] = []
    extra_in_csv:     list[dict] = []  # all extras
    teams_diff:       list[dict] = []
    matched = 0

    def find_match(target, pool):
        ta = (_asc(target["grade"]), _canon_sport(target["sport"]), target["gender"])
        for g in pool:
            if (_asc(g["grade"]), _canon_sport(g["sport"]), g["gender"]) == ta:
                return g
        return None

    for slot in all_slots:
        in_pdf = pdf_by_slot.get(slot, [])
        in_csv = csv_by_slot.get(slot, [])

        matched_csv_ids: set = set()

        for pg in in_pdf:
            cm = find_match(pg, in_csv)
            if cm:
                matched += 1
                matched_csv_ids.add(id(cm))
                if pg["teams"] != cm["teams"]:
                    teams_diff.append({
                        "slot": slot, "pdf_val": pg["teams"],
                        "csv_val": cm["teams"], "game": pg,
                    })
            else:
                missing_from_csv.append(pg)

        for cm in in_csv:
            if id(cm) not in matched_csv_ids:
                extra_in_csv.append(cm)

    # Split extras into expected vs unexpected
    expected_extras   = [g for g in extra_in_csv if g["sport"] in _EXPECTED_EXTRAS]
    unexpected_extras = [g for g in extra_in_csv if g["sport"] not in _EXPECTED_EXTRAS]

    # ── Print report ──────────────────────────────────────────────────────────
    SEP = "─" * 60
    print(f"\n{'═'*60}")
    print(f"AUDIT: games_from_pdf.csv  vs  docs/data/games.csv")
    print(f"{'═'*60}")
    print(f"  Matched:                    {matched:4d}")
    print(f"  Missing from CSV (PDF→CSV): {len(missing_from_csv):4d}")
    print(f"  Extra in CSV (no PDF match):{len(extra_in_csv):4d}  "
          f"({len(expected_extras)} expected from Gincana/Desafio/etc.)")
    print(f"  Teams mismatches:           {len(teams_diff):4d}")

    if missing_from_csv:
        print(f"\n{SEP}")
        print(f"⚠  IN PDF but MISSING from CSV ({len(missing_from_csv)}):")
        for g in sorted(missing_from_csv, key=lambda x: (x["date"], x["time"])):
            print(f"  {g['date']} {g['day']} {g['time']:6s} [{g['court']:28s}] "
                  f"{g['grade']:38s} | {g['sport']} {g['gender']} | {g['teams']}")

    if unexpected_extras:
        print(f"\n{SEP}")
        print(f"⚠  IN CSV but NOT in PDF — unexpected ({len(unexpected_extras)}):")
        for g in sorted(unexpected_extras, key=lambda x: (x["date"], x["time"])):
            print(f"  {g['date']} {g['day']} {g['time']:6s} [{g['court']:28s}] "
                  f"{g['grade']:38s} | {g['sport']} {g['gender']} | {g['teams']}")

    if expected_extras:
        print(f"\n{SEP}")
        print(f"ℹ  IN CSV but NOT in PDF — expected (Gincana/Desafio/Corrida/etc.) "
              f"({len(expected_extras)}):")
        for g in sorted(expected_extras, key=lambda x: (x["date"], x["time"])):
            print(f"  {g['date']} {g['day']} {g['time']:6s} [{g['court']:28s}] "
                  f"{g['grade']:38s} | {g['sport']}")

    if teams_diff:
        print(f"\n{SEP}")
        print(f"ℹ  TEAMS DIFFERENCES ({len(teams_diff)}) — data correct, formatting only:")
        for d in teams_diff:
            g = d["game"]
            print(f"  {g['date']} {g['time']:6s} [{g['court']:28s}] {g['grade']}")
            print(f"    PDF: {d['pdf_val']!r}")
            print(f"    CSV: {d['csv_val']!r}")

# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Table-based extractor for Jogos Monteiro 2026 PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--diag",  action="store_true",
                    help="Print page-by-page diagnostics, skip writing output")
    ap.add_argument("--audit", action="store_true",
                    help="Compare extracted output against docs/data/games.csv")
    ap.add_argument("--out",   default=str(OUTPUT_CSV),
                    metavar="PATH", help=f"Output CSV (default: {OUTPUT_CSV})")
    args = ap.parse_args()

    pdf_path = PDF_DIR / MAIN_PDF
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    if args.diag:
        print(f"DIAGNOSTIC: {pdf_path}")
    else:
        print(f"Extracting: {pdf_path}")

    games, errors = extract_pdf(pdf_path, diag=args.diag)

    if not args.diag:
        print(f"Extracted {len(games)} games, {len(errors)} warnings")

        out_path = Path(args.out)
        write_csv(games, out_path)
        print(f"Written:   {out_path}")

        if errors:
            ERRORS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(ERRORS_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(errors) + "\n")
            print(f"Warnings:  {ERRORS_FILE}  ({len(errors)} issues)")
        else:
            print("No warnings — all cells parsed cleanly.")

    if args.audit:
        if not REFERENCE.exists():
            print(f"ERROR: reference not found: {REFERENCE}", file=sys.stderr)
            sys.exit(1)
        csv_games = read_csv(REFERENCE)
        print(f"\nReference: {REFERENCE} ({len(csv_games)} games)")
        run_audit(games, csv_games)


if __name__ == "__main__":
    main()
