import sys
from pathlib import Path

# Garante que o diretório raiz do projeto esteja no PYTHONPATH para importações como "etl.*"
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Adiciona também o caminho raiz do Airflow para importações "plugins.*" em ambiente local/pytest
AIRFLOW_ROOT = ROOT / "airflow"
if AIRFLOW_ROOT.exists() and str(AIRFLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(AIRFLOW_ROOT))
