import os
import sys

import pytest


pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Airflow deve ser validado em Docker/Linux; não há suporte nativo ao Windows.",
)

def test_plugins_importable():
    # Evita erro de config do Airflow em ambiente local de teste
    os.environ.setdefault("AIRFLOW__CORE__SQL_ALCHEMY_CONN", "sqlite:////tmp/airflow.db")
    os.environ.setdefault("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", "sqlite:////tmp/airflow.db")
    # Verifica se os módulos de plugins são importáveis no contexto de testes
    import plugins.hooks.nasa_api_hook  # noqa: F401
    import plugins.operators.nasa_extract_operator  # noqa: F401
    import plugins.operators.nasa_transform_operator  # noqa: F401
    import plugins.operators.nasa_load_operator  # noqa: F401
