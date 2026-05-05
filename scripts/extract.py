#!/usr/bin/env python3
"""Extrator simples de texto de PDFs.

Uso:
  pip install -r requirements.txt
  python scripts/extract.py --input pdfs --output data/extracted.csv [--ocr]

Gera um CSV com colunas: `pdf`, `page`, `line_no`, `raw`.
"""
import os
import argparse
import pdfplumber
import pandas as pd

try:
    from pdf2image import convert_from_path
    import pytesseract
except Exception:
    # OCR é opcional; script funciona sem OCR
    convert_from_path = None
    pytesseract = None


def extract_text_from_pdf(path):
    rows = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if lines:
                for li, line in enumerate(lines, start=1):
                    rows.append({"pdf": os.path.basename(path), "page": i, "line_no": li, "raw": line})
            else:
                rows.append({"pdf": os.path.basename(path), "page": i, "line_no": 0, "raw": ""})
    return rows


def ocr_page_from_pdf(path, page_num):
    if convert_from_path is None or pytesseract is None:
        return ""
    imgs = convert_from_path(path, dpi=200, first_page=page_num, last_page=page_num)
    if not imgs:
        return ""
    text = pytesseract.image_to_string(imgs[0], lang='por')
    return text or ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='pdfs')
    parser.add_argument('--output', default='data/extracted.csv')
    parser.add_argument('--ocr', action='store_true', help='Usar OCR se página não contiver texto')
    args = parser.parse_args()

    os.makedirs(args.input, exist_ok=True)
    all_rows = []
    for fname in sorted(os.listdir(args.input)):
        if not fname.lower().endswith('.pdf'):
            continue
        path = os.path.join(args.input, fname)
        try:
            rows = extract_text_from_pdf(path)
            if args.ocr:
                # para linhas vazias, tenta OCR
                for r in rows:
                    if not r['raw']:
                        ocr_text = ocr_page_from_pdf(path, r['page'])
                        r['raw'] = ocr_text.strip()
            all_rows.extend(rows)
        except Exception as e:
            print(f"Erro em {path}: {e}")

    if not all_rows:
        print("Nenhum texto extraído.")
        return

    df = pd.DataFrame(all_rows)
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Saved {len(df)} rows to {args.output}")


if __name__ == '__main__':
    main()
