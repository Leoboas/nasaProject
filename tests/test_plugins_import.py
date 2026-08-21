import importlib
import os
import sys

import pytest


pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Airflow deve ser validado em Docker/Linux; não há suporte nativo ao Windows.",
)

def test_plugins_importable():
    os.environ.setdefault("AIRFLOW__CORE__SQL_ALCHEMY_CONN", "sqlite:////tmp/airflow.db")
    os.environ.setdefault("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", "sqlite:////tmp/airflow.db")

    for module_name in (
        "plugins.hooks.nasa_api_hook",
        "plugins.operators.nasa_extract_operator",
        "plugins.operators.nasa_transform_operator",
        "plugins.operators.nasa_load_operator",
    ):
        importlib.import_module(module_name)
