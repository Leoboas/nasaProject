"""Restore a project JSON backup into the local PostgreSQL database."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from etl.backup.json_email import BACKUP_TABLES
from etl.common.config import get_postgres_config


def _load_document(path: Path) -> dict[str, Any]:
    """Load and validate a versioned plain JSON or gzip JSON backup."""
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    document = json.loads(raw)
    if document.get("schema_version") != 1 or not isinstance(document.get("tables"), dict):
        raise ValueError("Formato de backup nao suportado")
    for table_name in BACKUP_TABLES:
        rows = document["tables"].get(table_name)
        if not isinstance(rows, list):
            raise ValueError(f"Tabela ausente ou invalida no backup: {table_name}")
        allowed = set(BACKUP_TABLES[table_name])
        if any(not isinstance(row, dict) or set(row) - allowed for row in rows):
            raise ValueError(f"Colunas invalidas no backup: {table_name}")
    return document


def restore_document(engine: Any, document: dict[str, Any]) -> dict[str, int]:
    """Upsert the supported tables in one transaction and reset the run ID sequence."""
    counts: dict[str, int] = {}
    with engine.begin() as connection:
        for table_name, columns in BACKUP_TABLES.items():
            rows = document["tables"][table_name]
            counts[table_name] = len(rows)
            if not rows:
                continue
            names = ", ".join(f'"{column}"' for column in columns)
            binds = ", ".join(
                f"CAST(:{column} AS JSONB)" if column == "details_json" else f":{column}"
                for column in columns
            )
            conflict_key = '"id", "close_approach_date"' if table_name == "asteroides_monitoria" else '"id"'
            update_columns = [column for column in columns if column not in {"id", "close_approach_date"}]
            if table_name == "etl_runs":
                update_columns = [column for column in columns if column != "id"]
            updates = ", ".join(
                f'"{column}" = EXCLUDED."{column}"' for column in update_columns
            )
            statement = text(
                f'INSERT INTO public."{table_name}" ({names}) VALUES ({binds}) '
                f"ON CONFLICT ({conflict_key}) DO UPDATE SET {updates}"
            )
            params = []
            for row in rows:
                item = {column: row.get(column) for column in columns}
                details = item.get("details_json")
                if details is not None and not isinstance(details, str):
                    item["details_json"] = json.dumps(details, ensure_ascii=False)
                params.append(item)
            connection.execute(statement, params)

        connection.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('public.etl_runs', 'id'), "
                "COALESCE((SELECT MAX(id) FROM public.etl_runs), 1), "
                "EXISTS(SELECT 1 FROM public.etl_runs))"
            )
        )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path, help="Arquivo nasa-etl-*.json.gz")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica o upsert. Sem esta opcao, apenas valida e mostra contagens.",
    )
    args = parser.parse_args()
    document = _load_document(args.backup)
    counts = {table: len(document["tables"][table]) for table in BACKUP_TABLES}
    if not args.apply:
        print(json.dumps({"validated": True, "rows": counts}, indent=2))
        print("Use --apply para gravar no PostgreSQL configurado no ambiente.")
        return

    engine = create_engine(get_postgres_config().sqlalchemy_url, pool_pre_ping=True)
    try:
        restored = restore_document(engine, document)
    finally:
        engine.dispose()
    print(json.dumps({"restored": restored}, indent=2))


if __name__ == "__main__":
    main()
