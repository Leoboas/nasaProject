"""Ponto de entrada do job diário usado por Docker/systemd."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path


# Permite executar diretamente com "python scripts/run_etl.py" no Windows,
# Linux e systemd, sem depender de PYTHONPATH externo.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.pipeline import run_daily_etl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executa uma coleta NASA NEO.")
    parser.add_argument(
        "--date",
        type=dt.date.fromisoformat,
        help="Data da coleta no formato YYYY-MM-DD (padrão: hoje).",
    )
    parser.add_argument(
        "--data-dir",
        help="Diretório para JSON bruto e CSV tratado (padrão: DATA_DIR ou data).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    loaded = run_daily_etl(run_date=args.date, data_dir=args.data_dir)
    print(f"ETL concluído. Registros carregados: {loaded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
