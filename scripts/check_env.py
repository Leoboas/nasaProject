"""Valida apenas as variáveis efetivamente usadas pelo pipeline atual."""

import os


REQUIRED_VARS = [
    "NASA_API_KEY",
    "POSTGRES_HOST",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
]


def main() -> int:
    missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
    if missing:
        print("Variáveis ausentes:", ", ".join(missing))
        return 1
    print("Todas as variáveis requeridas estão definidas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
