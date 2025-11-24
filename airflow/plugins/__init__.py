"""
Inicializa o namespace de plugins e garante que o diretório /opt/airflow/plugins
esteja no PYTHONPATH quando carregado fora do scheduler (ex.: pytest).
"""

import sys
from pathlib import Path

PLUGINS_DIR = Path(__file__).resolve().parent
if str(PLUGINS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGINS_DIR))
