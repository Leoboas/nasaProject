## Pipeline ETL NASA - Airflow + S3 + Postgres

Projeto exemplo de engenharia de dados com coleta diaria da NASA API (NEO/APOD), armazenamento em Data Lake S3, carga em Postgres (RDS) e orquestracao via Apache Airflow. Inclui IaC com Terraform, conteineres Docker, CI/CD no GitHub Actions, dashboards (Grafana/Power BI) e notebook exploratorio.

### Arquitetura (alto nivel)
- **Extracao**: operadores Airflow chamam a NASA API (HTTP) e gravam bruto em S3 (Free Tier) e `data/samples`.
- **Transformacao**: pipelines leves em Pandas para limpar e normalizar (ex.: asteroides proximos a Terra).
- **Carga**: gravacao em Postgres (tabela fato/dim) usando SQLAlchemy/psycopg2; pronto para BI.
- **Orquestracao**: DAG `nasa_etl_dag.py` com tasks de extract -> transform -> load; sensores de falha e SLAs.
- **Observabilidade**: logs no Airflow; Grafana provisionado; dashboards Power BI e Grafana template.
- **Infra**: Terraform para S3 + RDS + IAM + monitoramento Free Tier; conteineres via Docker Compose; CI no GitHub Actions.

### Como rodar localmente (dev)
1. Copie `.env.example` para `.env` e preencha `NASA_API_KEY`. Para usar RDS real/S3, preencha tambem as credenciais vindas do Terraform (veja secao abaixo).
2. Construa e suba conteineres: `docker-compose up -d --build`
3. Acesse Airflow em `http://localhost:8080` (admin/admin) e Grafana em `http://localhost:3000` (admin/admin).
4. Rode o DAG `nasa_etl_dag` manualmente ou agende diario.

### Estrutura principal
- `airflow/dags/`: DAG do ETL.
- `airflow/plugins/`: operadores e hooks customizados para NASA, transformacao e carga.
- `etl/`: modulos reutilizaveis (extracao, transformacao, carga, configs).
- `infra/terraform/`: IaC para S3, RDS, IAM, SNS, CloudWatch e Budget.
- `dashboards/`: templates Grafana/Power BI.
- `scripts/`: utilidades (rodar ETL local, popular .env a partir do Terraform).
- `tests/`: testes automatizados (pytest).

## Provisionamento AWS via Terraform

### Pre-requisitos
- Terraform instalado (>= 1.0)
- AWS CLI configurado com credenciais IAM (nao use root)
- Conta AWS com Free Tier ativo

### Passo a passo

1. Configure as variaveis no arquivo `infra/terraform/terraform.tfvars`:
   ```
   db_password = "SuaSenhaSegura123!"
   alert_email = "leoboas02@gmail.com"
   ```

2. Inicialize o Terraform:
   ```
   cd infra/terraform
   terraform init
   ```

3. Valide a configuracao:
   ```
   terraform validate
   terraform plan
   ```

4. Provisione a infraestrutura:
   ```
   terraform apply
   ```

5. Capture as credenciais geradas:
   ```
   terraform output -json > ../terraform_outputs.json
   ```

6. Popule o arquivo `.env` automaticamente:
   ```
   cd ..
   python scripts/populate_env.py
   ```

7. Suba o ambiente com Docker:
   ```
   docker-compose up -d --build
   ```

### Monitoramento de custos
- Voce recebera alertas por email quando:
  - Bucket S3 atingir ~4.5 GB (90% do limite de 5 GB do Free Tier).
  - Custo mensal atingir $0.80 (80% do budget) ou $1.00 (100%).
  - RDS storage ficar abaixo de 2 GB livres (~18 GB usados de 20 GB).

### Destruir infraestrutura
```
cd infra/terraform
terraform destroy
```
