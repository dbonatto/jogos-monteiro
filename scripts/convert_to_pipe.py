#!/usr/bin/env python3
"""Converte CSV revisado para formato pipe-separado para use no index.html."""
import csv
import argparse

def csv_to_pipe_format(csv_path: str) -> str:
    """Converte CSV revisado em formato pipe-separado (date|day|period|...)."""
    lines = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Garante que temos os campos necessários
            fields = [
                row.get('date', ''),
                row.get('day', ''),
                row.get('period', ''),
                row.get('location', ''),
                row.get('time', ''),
                row.get('court', ''),
                row.get('grade', ''),
                row.get('sport', ''),
                row.get('gender', ''),
                row.get('teams', '')
            ]
            
            # Pula linhas com campos críticos vazios
            if not (fields[0] and fields[8] and fields[9]):  # date, gender, teams
                continue
            
            line = '|'.join(fields)
            lines.append(line)
    
    return '\n'.join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, help='CSV revisado (exportado da UI)')
    parser.add_argument('--output', default='data/rawData.txt', help='Saída em formato pipe')
    args = parser.parse_args()
    
    pipe_data = csv_to_pipe_format(args.input)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(pipe_data)
    
    lines = pipe_data.split('\n')
    print(f"Convertidos {len(lines)} registros para formato pipe-separado")
    print(f"Salvo em: {args.output}")
    print(f"\nPrimeiro registro:\n{lines[0]}")
    print(f"\nÚltimo registro:\n{lines[-1]}")
    print(f"\n--- Copie o conteúdo abaixo para o const rawData no index.html ---\n")
    print(f"const rawData = `\n{pipe_data}\n`;")

if __name__ == '__main__':
    main()
