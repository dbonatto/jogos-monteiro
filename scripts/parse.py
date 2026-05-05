#!/usr/bin/env python3
"""Parser robusto de eventos extraídos de PDFs.

Transforma data/extracted.csv em data/parsed.csv com campos estruturados:
  date, day, period, location, time, court, grade, sport, gender, teams, source, confidence

Uso:
  python3 scripts/parse.py --input data/extracted.csv --output data/parsed.csv
"""
import os
import re
import argparse
import pandas as pd
from typing import Dict, List, Optional, Tuple

# Padrões e mapeamentos
DAYS_PT = {
    'segunda': 'Segunda', 'segunda-feira': 'Segunda',
    'terça': 'Terça', 'terça-feira': 'Terça',
    'quarta': 'Quarta', 'quarta-feira': 'Quarta',
    'quinta': 'Quinta', 'quinta-feira': 'Quinta',
    'sexta': 'Sexta', 'sexta-feira': 'Sexta',
}

PERIODS = ['Manhã', 'Tarde', 'Noite', 'Integral']

TEAMS = ['VERMELHO', 'ROXO', 'VERDE', 'AZUL', 'AMARELO', 'BRANCO']

SPORTS = [
    'Basquete', 'Basquetebol', 'Futsal', 'Futebol', 'Voleibol', 'Vôlei',
    'Handebol', 'Queimada', 'Dodgeball', 'Bola Por Cima', 'Atletismo',
    'Salto em Altura', 'Corrida', 'Natação', 'Xadrez', 'Ping Pong'
]

GENDERS = ['Masc', 'Fem', 'Misto']

GRADES_EM = [
    '1º ano Ensino Médio', '2º ano Ensino Médio', '3º ano Ensino Médio',
    '1º EM', '2º EM', '3º EM'
]
GRADES_EFII = [
    '6º ano Ensino Fundamental II', '7º ano Ensino Fundamental II',
    '8º ano Ensino Fundamental II', '9º ano Ensino Fundamental II',
    '6º EF II', '7º EF II', '8º EF II', '9º EF II'
]
GRADES_EFI = [
    '1º ano Ensino Fundamental I', '2º ano Ensino Fundamental I',
    '3º ano Ensino Fundamental I',
    '1º EF I', '2º EF I', '3º EF I'
]

class EventParser:
    def __init__(self):
        self.events: List[Dict] = []
        self.current_context: Dict = {}

    def extract_date(self, text: str) -> Optional[str]:
        """Extrai data em formato DD/MM de texto."""
        match = re.search(r'(\d{1,2})[/-](\d{1,2})', text)
        if match:
            day, month = match.groups()
            return f"{int(day):02d}/{int(month):02d}"
        return None

    def extract_time(self, text: str) -> Optional[str]:
        """Extrai hora em formato HHhMM de texto."""
        # Tenta HHh ou HH:MM ou HHhMM
        match = re.search(r'(\d{1,2})[h:](\d{2})?', text, re.IGNORECASE)
        if match:
            h, m = match.groups()
            m = m or '00'
            return f"{int(h):02d}h{int(m):02d}"
        match = re.search(r'(\d{1,2})h', text, re.IGNORECASE)
        if match:
            return f"{int(match.group(1)):02d}h00"
        return None

    def extract_day(self, text: str) -> Optional[str]:
        """Extrai dia da semana normalizado."""
        text_lower = text.lower()
        for pt, en in DAYS_PT.items():
            if pt in text_lower:
                return en
        return None

    def extract_period(self, text: str) -> Optional[str]:
        """Extrai período (Manhã, Tarde, Noite)."""
        text_lower = text.lower()
        for period in PERIODS:
            if period.lower() in text_lower:
                return period
        return None

    def extract_gender(self, text: str) -> Optional[str]:
        """Extrai gênero (Masc, Fem, Misto)."""
        text_upper = text.upper()
        if 'FEM' in text_upper or 'FEMININO' in text_upper:
            return 'Fem'
        if 'MASC' in text_upper or 'MASCULINO' in text_upper:
            return 'Masc'
        if 'MISTO' in text_upper:
            return 'Misto'
        return None

    def extract_sport(self, text: str) -> Optional[str]:
        """Extrai esporte."""
        text_lower = text.lower()
        for sport in SPORTS:
            if sport.lower() in text_lower:
                return sport
        return None

    def extract_grade(self, text: str) -> Optional[str]:
        """Extrai série/ano escolar."""
        for grade in GRADES_EM + GRADES_EFII + GRADES_EFI:
            if grade.lower() in text.lower():
                return grade
        # Tenta extrair padrão "Nº ano"
        match = re.search(r"(\d)º\s*(?:ano\s+)?(?:ensino\s+)?(\w+)?", text, re.IGNORECASE)
        if match:
            year, level = match.groups()
            if level:
                level = 'Ensino Médio' if 'médio' in level.lower() else 'Ensino Fundamental II'
            else:
                level = 'Ensino Fundamental II'
            return f"{year}º ano {level}"
        return None

    def extract_teams(self, text: str) -> Optional[str]:
        """Extrai matchup de times (E.g., 'VERMELHO X ROXO')."""
        text_upper = text.upper()
        teams_found = []
        for team in TEAMS:
            if team in text_upper:
                teams_found.append(team)
        if len(teams_found) >= 2:
            return f"{teams_found[0]} X {teams_found[1]}"
        # Tenta padrão "X" ou "x"
        if ' X ' in text_upper or ' x ' in text.lower():
            parts = re.split(r'\s+[Xx]\s+', text)
            if len(parts) == 2:
                return f"{parts[0].strip().upper()} X {parts[1].strip().upper()}"
        return None

    def extract_location(self, text: str) -> Optional[str]:
        """Extrai local/quadra."""
        keywords = [
            'Quadra', 'Pátio', 'Ginásio', 'Teatro', 'Sala', 'Grama',
            'Campo', 'Sintética', 'Coberta', 'Externa', 'Open', 'Área'
        ]
        for kw in keywords:
            if kw.lower() in text.lower():
                # Extrai a sequência contendo a palavra-chave
                match = re.search(rf'[A-Za-z\s]+{re.escape(kw)}[A-Za-z\s]*', text)
                if match:
                    return match.group(0).strip()
        return None

    def parse_raw_line(self, raw: str, pdf: str, page: int) -> Optional[Dict]:
        """Tenta parsear uma linha bruta em estrutura de evento."""
        # Lida com valores NaN (pandas)
        if not isinstance(raw, str) or not raw or len(raw) < 3:
            return None

        event = {
            'date': self.extract_date(raw),
            'day': self.extract_day(raw),
            'period': self.extract_period(raw),
            'location': self.extract_location(raw),
            'time': self.extract_time(raw),
            'court': None,  # Pode ser extraído de location
            'grade': self.extract_grade(raw),
            'sport': self.extract_sport(raw),
            'gender': self.extract_gender(raw),
            'teams': self.extract_teams(raw),
            'source': f"{pdf}#{page}",
            'confidence': self._compute_confidence(event if 'event' in locals() else {})
        }
        
        # Tira None values
        event = {k: v for k, v in event.items() if v is not None}
        
        # Rejeita linhas sem campos críticos
        if not any([event.get('date'), event.get('time'), event.get('sport')]):
            return None
        
        return event

    def _compute_confidence(self, event: Dict) -> float:
        """Calcula score de confiança (0.0 a 1.0)."""
        critical = ['date', 'day', 'period', 'time', 'sport', 'gender', 'teams']
        filled = sum(1 for k in critical if k in event and event[k])
        return filled / len(critical) if critical else 0.0


def parse_extracted_csv(input_path: str) -> pd.DataFrame:
    """Lê CSV extraído e retorna DataFrame com eventos parseados."""
    df_raw = pd.read_csv(input_path)
    parser = EventParser()
    
    parsed_events = []
    for _, row in df_raw.iterrows():
        event = parser.parse_raw_line(row['raw'], row['pdf'], row['page'])
        if event:
            event['source_pdf'] = row['pdf']
            event['source_page'] = row['page']
            event['source_line'] = row['line_no']
            parsed_events.append(event)
    
    df_parsed = pd.DataFrame(parsed_events)
    
    # Normaliza colunas
    cols = [
        'date', 'day', 'period', 'location', 'time', 'court', 'grade',
        'sport', 'gender', 'teams', 'source', 'confidence', 'source_pdf', 'source_page', 'source_line'
    ]
    for col in cols:
        if col not in df_parsed.columns:
            df_parsed[col] = None
    
    return df_parsed[cols]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='data/extracted.csv')
    parser.add_argument('--output', default='data/parsed.csv')
    args = parser.parse_args()

    df = parse_extracted_csv(args.input)
    
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    df.to_csv(args.output, index=False)
    
    print(f"Parsed {len(df)} events")
    print(f"Avg confidence: {df['confidence'].mean():.2f}")
    print(f"Saved to {args.output}")
    
    # Mostra amostra
    print(f"\nAmostra (primeiras 10 linhas com teams):")
    sample = df[df['teams'].notna()].head(10)
    for _, row in sample.iterrows():
        print(f"  {row['date']} {row['period']} | {row['sport']} {row['gender']} | {row['teams']}")


if __name__ == '__main__':
    main()
