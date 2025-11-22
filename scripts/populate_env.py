import argparse
import json
from pathlib import Path
from typing import Dict


OUTPUTS_PATH = Path("terraform_outputs.json")
ENV_PATH = Path(".env")
ENV_TEMPLATE = Path(".env.example")


def parse_env(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        if not line or line.strip().startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            env[key.strip()] = val.strip()
    return env


def write_env(env: Dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in env.items()]
    ENV_PATH.write_text("\n".join(lines))


def load_outputs(path: Path) -> Dict[str, str]:
    data = json.loads(path.read_text())
    outputs = {}
    for key, value in data.items():
        outputs[key] = value.get("value")
    return outputs


def main():
    parser = argparse.ArgumentParser(
        description="Atualiza o .env a partir dos outputs do Terraform (terraform_outputs.json)."
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=OUTPUTS_PATH,
        help="Caminho para o arquivo terraform_outputs.json",
    )
    args = parser.parse_args()

    if not args.outputs.exists():
        raise FileNotFoundError(
            f"Arquivo de outputs não encontrado: {args.outputs}. Execute `terraform output -json > ../terraform_outputs.json`."
        )

    outputs = load_outputs(args.outputs)
    env = parse_env(ENV_TEMPLATE)
    env.update(parse_env(ENV_PATH))

    required_map = {
        "AWS_ACCESS_KEY_ID": outputs.get("iam_access_key_id"),
        "AWS_SECRET_ACCESS_KEY": outputs.get("iam_secret_access_key"),
        "AWS_REGION": outputs.get("aws_region", "us-east-1"),
        "AWS_BUCKET_NAME": outputs.get("bucket_name"),
        "POSTGRES_HOST": outputs.get("postgres_host"),
        "POSTGRES_PORT": outputs.get("postgres_port"),
        "POSTGRES_DB": outputs.get("postgres_database"),
        "POSTGRES_USER": outputs.get("postgres_username"),
    }

    missing_outputs = [k for k, v in required_map.items() if v in (None, "")]
    if missing_outputs:
        raise ValueError(f"Outputs ausentes no terraform_outputs.json: {', '.join(missing_outputs)}")

    env.update({k: str(v) for k, v in required_map.items()})

    warnings = []
    if "POSTGRES_PASSWORD" not in env or not env["POSTGRES_PASSWORD"]:
        warnings.append("Defina POSTGRES_PASSWORD (use o mesmo de terraform.tfvars).")
        env["POSTGRES_PASSWORD"] = "CHANGE_ME"
    if "NASA_API_KEY" not in env or not env["NASA_API_KEY"]:
        warnings.append("Defina NASA_API_KEY com sua chave da API da NASA.")

    write_env(env)

    print("Arquivo .env atualizado com outputs do Terraform.")
    if warnings:
        print("Avisos:")
        for w in warnings:
            print(f"- {w}")


if __name__ == "__main__":
    main()
