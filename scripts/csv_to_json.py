#!/usr/bin/env python3
"""Converte CSV extraído em JSON estruturado para uso no app."""
import json
import csv
import argparse

def csv_to_json(csv_path: str) -> list:
    """Converte extracted.csv em array de objetos JSON."""
    events = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Tenta parsear o 'raw' para extrair dados estruturados
            raw = row.get('raw', '').strip()
            
            # Padrão esperado: data|dia|período|local|hora|quadra|série|esporte|gênero|times
            if '|' in raw:
                parts = [p.strip() for p in raw.split('|')]
                if len(parts) >= 10:
                    event = {
                        'date': parts[0],
                        'day': parts[1],
                        'period': parts[2],
                        'location': parts[3],
                        'time': parts[4],
                        'court': parts[5],
                        'grade': parts[6],
                        'sport': parts[7],
                        'gender': parts[8],
                        'teams': parts[9]
                    }
                    events.append(event)
    
    return events

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='data/extracted.csv')
    parser.add_argument('--output', default='data/games.json')
    args = parser.parse_args()
    
    events = csv_to_json(args.input)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    
    print(f"Converted {len(events)} events to {args.output}")
    if events:
        print(f"\nSample event:\n{json.dumps(events[0], indent=2, ensure_ascii=False)}")

if __name__ == '__main__':
    main()
