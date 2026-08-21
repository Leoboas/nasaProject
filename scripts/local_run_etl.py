"""Atalho local para a mesma execução leve usada em produção."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl.pipeline import run_daily_etl


def main() -> int:
    loaded = run_daily_etl()
    print(f"ETL local concluído. Registros carregados: {loaded}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
