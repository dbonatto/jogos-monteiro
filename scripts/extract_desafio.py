#!/usr/bin/env python3
"""extract_desafio.py — Parser for "2026_EFII DESAFIO ACADÊMICO .pdf".

Structure:
  - Single page, plain text + one small table
  - Table: BANCA | room_number; three color rows: VERDE | room, VERMELHO | room, ROXO | room
  - Header text: date ("06 de maio de 2026"), day ("quarta-feira"), time ("das 14h às 18h")
  - Grades: "6º ao 8º anos do EFII" → each color participates with each grade 6-8

Output: one row per grade (6º, 7º, 8º) × color.
The "teams" field is "-" (no opponent; this is an individual event).
court = "Sala 101" (extracted from text or table header).
sport = "Desafio Acadêmico", gender = "Misto".

Each team (cor) competes independently, so we emit:
  date|day|period|location|time|court|grade|sport|gender|teams
One row per grade per turma — we use the turma suffix from games.csv convention.

Usage:
  python3 scripts/extract_desafio.py [--out data/desafio_from_pdf.csv] [--diag]
"""

import re, sys, argparse, unicodedata, glob
from pathlib import Path
import pdfplumber

PDF_GLOB   = "pdfs/*DESAFIO*"
OUTPUT_CSV = Path("data/desafio_from_pdf.csv")

FIELD_ORDER = ("date", "day", "period", "location", "time", "court",
               "grade", "sport", "gender", "teams")

# Canonical turma codes for EFII grades (from games.csv convention)
# grade number → list of turma suffixes present in games.csv
TURMAS_BY_GRADE = {
    6: ["61", "62", "63"],
    7: ["71", "72", "73"],
    8: ["81", "82", "83"],
}


def _asc(s: str) -> str:
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()


def parse_desafio(pdf_path: Path, diag: bool = False) -> list[dict]:
    games: list[dict] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""

        if diag:
            print("FULL TEXT:")
            print(text)

        # ── Date ──────────────────────────────────────────────────────────────
        date_m = re.search(r"(\d{1,2})\s+de\s+maio\s+de\s+2026", text, re.IGNORECASE)
        date   = f"{int(date_m.group(1)):02d}/05" if date_m else "06/05"

        # ── Day ───────────────────────────────────────────────────────────────
        day_m = re.search(
            r"(segunda|terça|terca|quarta|quinta|sexta)(?:-feira)?",
            text, re.IGNORECASE
        )
        DAY_CANON = {"segunda":"Segunda","terca":"Terça","terca":"Terça",
                     "quarta":"Quarta","quinta":"Quinta","sexta":"Sexta"}
        day = DAY_CANON.get(_asc(day_m.group(1)).replace("ç","c"), "Quarta") if day_m else "Quarta"

        # ── Time ──────────────────────────────────────────────────────────────
        time_m = re.search(r"das\s+(\d{1,2})h\s+(?:às|as)", text, re.IGNORECASE)
        time_str = f"{int(time_m.group(1))}h00" if time_m else "14h00"

        # ── Period ────────────────────────────────────────────────────────────
        h = int(re.match(r"(\d+)", time_str).group(1))
        period = "Manhã" if h < 13 else "Tarde" if h < 18 else "Noite"

        # ── Court: extract room number from table BANCA row ───────────────────
        tables = page.extract_tables()
        banca_room = "101"   # default — matches what's in games.csv
        for table in tables:
            for row in table:
                if row and str(row[0]).strip().upper() == "BANCA":
                    val = str(row[1]).strip() if len(row) > 1 and row[1] else "101"
                    # val may be a room number like "101"
                    if re.match(r"\d+", val):
                        banca_room = val
                    break

        court    = f"Sala {banca_room}"
        location = "Colégio Monteiro Lobato"

        if diag:
            print(f"\nParsed header: date={date} day={day} time={time_str} "
                  f"period={period} court={court}")

        # ── Grades: 6º ao 8º years, one record per grade × turma ─────────────
        for grade_num, turmas in TURMAS_BY_GRADE.items():
            grade_name = f"{grade_num}º ano Ensino Fundamental II"
            for turma in turmas:
                grade_with_turma = f"{grade_name} (Turma {turma})"
                games.append({
                    "date":     date,
                    "day":      day,
                    "period":   period,
                    "location": location,
                    "time":     time_str,
                    "court":    court,
                    "grade":    grade_with_turma,
                    "sport":    "Desafio Acadêmico",
                    "gender":   "Misto",
                    "teams":    "-",
                })

    if diag:
        print(f"\nOutput ({len(games)} records):")
        for g in games:
            print(f"  {g['date']} {g['day']} {g['time']} [{g['court']}] "
                  f"{g['grade']} | {g['sport']}")

    return games


def write_csv(games: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for g in games:
            f.write("|".join(g[k] for k in FIELD_ORDER) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Desafio Acadêmico EFII PDF extractor")
    ap.add_argument("--diag", action="store_true")
    ap.add_argument("--out", default=str(OUTPUT_CSV), metavar="PATH")
    args = ap.parse_args()

    matches = glob.glob(PDF_GLOB)
    if not matches:
        print(f"ERROR: no PDF matching {PDF_GLOB!r}", file=sys.stderr)
        sys.exit(1)
    pdf_path = Path(matches[0])

    games = parse_desafio(pdf_path, diag=args.diag)

    if not args.diag:
        out = Path(args.out)
        write_csv(games, out)
        print(f"Extracted {len(games)} desafio records → {out}")


if __name__ == "__main__":
    main()
