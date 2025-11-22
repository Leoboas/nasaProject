import os

REQUIRED_VARS = [
    "NASA_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "S3_BUCKET",
]


def main():
    missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
    if missing:
        print("Variáveis ausentes:", ", ".join(missing))
    else:
        print("Todas as variáveis requeridas estão definidas.")


if __name__ == "__main__":
    main()
