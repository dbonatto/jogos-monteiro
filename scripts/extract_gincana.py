#!/usr/bin/env python3
"""extract_gincana.py — Parser for "2026 GINCANA EFI-1º a 3º (1).pdf".

The Gincana PDF has a completely different structure from the main schedule:
  - No time-per-game rows; each table column is an entire session block
  - Each block has: DATA, LOCAL, HORÁRIO, TURMAS / PÚBLICO (class codes), ...
  - "TURMAS" cell encodes class codes (e.g. "41, 42 e 43") THEN participant counts
    ("Roxo - 22 Vermelho - 20") — we only want the class codes
  - Some tables contain MULTIPLE session blocks (Quinta moments 1 and 2)
    separated by a section-header row within the same table
  - The 04/05 page has one block captured as a table and a second block only in
    raw text (pdfplumber limitation) — we detect and parse it from text
  - No teams or gender — it's always Misto
  - Sport = "Gincana"

Output format (pipe-separated, same as games.csv):
  date|day|period|location|time|court|grade|sport|gender|teams

Uso:
  python3 scripts/extract_gincana.py [--out data/gincana_from_pdf.csv] [--diag]
"""

import re, sys, argparse, unicodedata
from pathlib import Path
import pdfplumber

PDF_PATH   = Path("pdfs/2026 GINCANA EFI-1º a 3º (1).pdf")
OUTPUT_CSV = Path("data/gincana_from_pdf.csv")

FIELD_ORDER = ("date", "day", "period", "location", "time", "court",
               "grade", "sport", "gender", "teams")

# Known school-calendar dates → canonical day name
DATE_TO_DAY: dict[str, str] = {
    "04/05": "Segunda",
    "05/05": "Terça",
    "06/05": "Quarta",
    "07/05": "Quinta",
    "08/05": "Sexta",
}

# ── Normalization helpers ──────────────────────────────────────────────────────

def _asc(s: str) -> str:
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()


DAY_CANON = {
    "segunda": "Segunda", "terca": "Terça", "quarta": "Quarta",
    "quinta": "Quinta",   "sexta": "Sexta",
}

LOCATION_MAP = {
    "area em frente":   "Colégio Monteiro Lobato",
    "quadrinha":        "Colégio Monteiro Lobato",
    "quadra coberta":   "Colégio Monteiro Lobato",
    "quadra grande":    "Colégio Monteiro Lobato",
    "quadra voleibol":  "Colégio Monteiro Lobato",
    "quadra sintetica": "Monteiro Open",
    "quadras de areia": "Monteiro Open",
    "open":             "Monteiro Open",
}

COURT_MAP = {
    "area em frente ao teatro": "Área em frente ao teatro",
    "quadrinha":                "Quadrinha de Vôlei",
    "quadras de areia":         "Quadras de Areia",
    "quadra coberta":           "Quadra Coberta",
    "quadra sintética open":    "Quadra Sintética",
    "quadra sintetica open":    "Quadra Sintética",
    "quadra grande open":       "Quadra Grande",
    "quadra grande (chuva":     "Quadra Grande",
    "quadra grande":            "Quadra Grande",
    "quadra voleibol":          "Quadra Voleibol",
}

_ORD = {1: "1º", 2: "2º", 3: "3º", 4: "4º", 5: "5º"}

# Color words that mark the start of participant counts — stop turma parsing here
_COLOR_STOP = re.compile(r"\b(roxo|vermelho|verde|azul|amarelo)\b", re.IGNORECASE)


def normalize_location(raw: str) -> str:
    k = _asc(raw).strip()
    # Longer keys first (more specific match)
    for fragment, loc in sorted(LOCATION_MAP.items(), key=lambda x: -len(x[0])):
        if fragment in k:
            return loc
    return "Colégio Monteiro Lobato"


def normalize_court(raw: str) -> str:
    k = _asc(raw).strip()
    for fragment, court in sorted(COURT_MAP.items(), key=lambda x: -len(x[0])):
        if fragment in k:
            return court
    return raw.strip().title()


def derive_period(time_raw: str) -> str:
    m = re.search(r"(\d{1,2})\s*[hH]", time_raw or "")
    if m:
        h = int(m.group(1))
        return "Manhã" if h < 13 else "Tarde" if h < 18 else "Noite"
    return "Manhã"


def parse_start_time(time_raw: str) -> str:
    """Extract start time → HhMM format."""
    m = re.search(r"(\d{1,2})[hH](\d{2})?", time_raw or "")
    if m:
        return f"{int(m.group(1))}h{m.group(2) or '00'}"
    return "00h00"


def parse_day_from_header(section_header: str) -> str:
    """Extract day from section header text like 'GINCANA EF I - TERÇA-FEIRA 05/05'."""
    m = re.search(
        r"(SEGUNDA|TERÇA|TERCA|QUARTA|QUINTA|SEXTA|5ª\s*FEIRA|5A\s*FEIRA)",
        section_header, re.IGNORECASE
    )
    if m:
        raw = m.group(1)
        if re.match(r"5", raw):
            return "Quinta"
        return DAY_CANON.get(_asc(raw).replace("ç", "c"), raw.title())
    return ""


def parse_date(raw: str) -> str:
    m = re.search(r"(\d{1,2})/(\d{2})", raw or "")
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}"
    return ""


def parse_grade_codes(turmas_raw: str) -> list[str]:
    """
    Convert class codes to canonical grade names with turma suffix.

    Codes are 2-digit: tens = year, units = class (11–53).
    IMPORTANT: Stop parsing at the first color word (participant counts follow).
    """
    # Truncate at the first color word (e.g. "41, 42 e 43 Roxo - 22 ...")
    stop = _COLOR_STOP.search(turmas_raw or "")
    relevant = turmas_raw[:stop.start()].strip() if stop else (turmas_raw or "").strip()

    # Also handle "/" separator (e.g. "11/21/31")
    relevant = relevant.replace("/", ",")

    codes = re.findall(r"\b([1-5]\d)\b", relevant)
    grades = []
    seen: set[str] = set()
    for code in codes:
        if code in seen:
            continue
        seen.add(code)
        year = int(code[0])
        if year in _ORD:
            grades.append(
                f"{_ORD[year]} ano Ensino Fundamental I (Turma {code})"
            )
    return grades


# ── Table splitting ────────────────────────────────────────────────────────────

def split_table_at_sections(table: list[list]) -> list[tuple[str, list[list]]]:
    """
    Some tables (Quinta) embed multiple session blocks separated by a header row.
    Split into sub-tables, each prefixed with its section header string.

    Returns list of (section_header, sub_table_rows).
    """
    sections: list[tuple[str, list[list]]] = []
    current_header = ""
    current_rows: list[list] = []

    for row in table:
        if not row:
            continue
        first = str(row[0]).strip() if row[0] else ""
        # A section header row: non-empty first cell that isn't a DATA/LOCAL/etc key
        # AND the rest of the cells are None/empty
        is_section_hdr = (
            first
            and first.upper() not in ("DATA", "LOCAL", "HORÁRIO", "HORARIO",
                                       "TURMAS", "TURMA", "PÚBLICO", "PUBLICO",
                                       "ATIVIDADE", "PROFESSOR", "MESÁRIOS", "MESARIOS")
            and all(not (row[c] if c < len(row) else None) for c in range(1, len(row)))
        )
        if is_section_hdr and current_rows:
            sections.append((current_header, current_rows))
            current_header = first
            current_rows = []
        elif is_section_hdr:
            current_header = first
        else:
            current_rows.append(row)

    if current_rows:
        sections.append((current_header, current_rows))

    return sections


# ── Block parser ───────────────────────────────────────────────────────────────

def table_to_dict(rows: list[list]) -> dict[str, list[str]]:
    """First col = key, remaining cols = values per session."""
    result: dict[str, list[str]] = {}
    for row in rows:
        if not row or not row[0]:
            continue
        key = str(row[0]).strip().upper()
        vals = [str(c).strip() if c else "" for c in row[1:]]
        if key and key not in result:
            result[key] = vals
    return result


def parse_block(tbl_dict: dict, section_header: str) -> list[dict]:
    """Parse one session block (one table or sub-table) into game records."""
    games = []

    dates    = tbl_dict.get("DATA", [])
    locals_  = tbl_dict.get("LOCAL", [])
    horarios = tbl_dict.get("HORÁRIO", tbl_dict.get("HORARIO", []))
    turmas   = tbl_dict.get("TURMAS", tbl_dict.get("PÚBLICO", tbl_dict.get("PUBLICO", [])))

    n_cols = max(len(dates), len(locals_), len(horarios), len(turmas), 1)

    for col in range(n_cols):
        date_raw  = (dates[col]    if col < len(dates)    else "").replace("\n", " ")
        local_raw = (locals_[col]  if col < len(locals_)  else "").replace("\n", " ")
        hora_raw  = (horarios[col] if col < len(horarios) else "").replace("\n", " ")
        turma_raw = (turmas[col]   if col < len(turmas)   else "").replace("\n", " ")

        # Skip null/empty columns (e.g. spacer columns in Quinta table)
        if not local_raw and not turma_raw:
            continue

        date = parse_date(date_raw)
        if not date:
            # For "5ª FEIRA Manhã" style dates, try to get date from section header
            m = re.search(r"(\d{1,2})/(\d{2})", section_header)
            if m:
                date = f"{int(m.group(1)):02d}/{m.group(2)}"
        if not date:
            continue

        # Day: calendar lookup is authoritative; fall back to section header, then DATA cell
        day = (DATE_TO_DAY.get(date)
               or parse_day_from_header(section_header)
               or parse_day_from_header(date_raw))

        location = normalize_location(local_raw)
        court    = normalize_court(local_raw)
        time_str = parse_start_time(hora_raw)
        period   = derive_period(hora_raw)
        grades   = parse_grade_codes(turma_raw)

        if not grades:
            continue

        for grade in grades:
            games.append({
                "date":     date,
                "day":      day,
                "period":   period,
                "location": location,
                "time":     time_str,
                "court":    court,
                "grade":    grade,
                "sport":    "Gincana",
                "gender":   "Misto",
                "teams":    "-",
            })

    return games


# ── Main extractor ─────────────────────────────────────────────────────────────

def extract(pdf_path: Path, diag: bool = False) -> list[dict]:
    games: list[dict] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text   = page.extract_text() or ""
            tables = page.extract_tables()

            if diag:
                print(f"\n{'='*50}")
                print(f"PAGE {page_num}: {len(tables)} tables")

            # Find section headers from page text to use as fallback date/day context
            # Lines like "GINCANA EF I - TERÇA-FEIRA MANHÃ" or "GINCANA EF I - QUINTA-FEIRA 07/05 2ºMOMENTO"
            section_headers = re.findall(
                r"GINCANA\s+EF\s+I\s*[-–]\s*[^\n]+",
                text, re.IGNORECASE
            )
            if diag:
                print(f"  Section headers in text: {section_headers}")

            # Track which sections we covered with tables
            covered_sections: list[str] = []

            for ti, table in enumerate(tables):
                if not table:
                    continue

                # Skip tables that don't have DATA/HORÁRIO/PÚBLICO as first-column keys
                known_keys = {"DATA", "HORÁRIO", "HORARIO", "LOCAL", "TURMAS",
                              "PÚBLICO", "PUBLICO", "ATIVIDADE"}
                first_keys = {str(row[0]).strip().upper() for row in table if row and row[0]}
                if not first_keys.intersection(known_keys):
                    if diag:
                        print(f"  Table {ti}: skipped (keys={first_keys})")
                    continue

                # Split the table at embedded section headers
                sub_sections = split_table_at_sections(table)

                for sec_hdr, rows in sub_sections:
                    # Determine effective_header for day/date context:
                    # 1. If sec_hdr is non-empty (came from an embedded table header row),
                    #    use it directly — it's already authoritative.
                    # 2. If sec_hdr is empty, find the page-level section header whose date
                    #    matches the dates in the DATA row of this sub-table.
                    if sec_hdr:
                        effective_header = sec_hdr
                    else:
                        # Collect dates from the DATA row of this sub-table
                        data_dates: set[str] = set()
                        for row in rows:
                            if row and row[0] and str(row[0]).strip().upper() == "DATA":
                                for cell in row[1:]:
                                    m = re.search(r"(\d{1,2})/(\d{2})", str(cell or ""))
                                    if m:
                                        data_dates.add(f"{m.group(1)}/{m.group(2)}")
                                break
                        effective_header = section_headers[0] if section_headers else ""
                        for sh in section_headers:
                            if any(d in sh for d in data_dates):
                                effective_header = sh
                                break

                    tbl_dict = table_to_dict(rows)
                    block_games = parse_block(tbl_dict, effective_header)
                    covered_sections.append(effective_header)

                    if diag:
                        print(f"  Table {ti} / sec={sec_hdr!r}: → {len(block_games)} records")
                        for g in block_games:
                            print(f"    {g['date']} {g['day']:6s} {g['time']:6s} "
                                  f"[{g['court']:28s}] {g['grade']}")

                    games.extend(block_games)

    return games


def write_csv(games: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for g in games:
            f.write("|".join(g[k] for k in FIELD_ORDER) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Gincana EFI PDF extractor")
    ap.add_argument("--diag", action="store_true")
    ap.add_argument("--out", default=str(OUTPUT_CSV), metavar="PATH")
    args = ap.parse_args()

    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found: {PDF_PATH}", file=sys.stderr)
        sys.exit(1)

    games = extract(PDF_PATH, diag=args.diag)

    if not args.diag:
        out = Path(args.out)
        write_csv(games, out)
        print(f"Extracted {len(games)} gincana records → {out}")
    else:
        print(f"\nTotal records: {len(games)}")


if __name__ == "__main__":
    main()

