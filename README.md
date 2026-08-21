# NASA NEO ETL — monitoramento de asteroides

Pipeline de dados em Python que consulta a API NASA Near Earth Object (NEO),
normaliza os eventos, filtra alertas relevantes e persiste resultados de modo
idempotente no PostgreSQL.

O repositório oferece dois modos intencionais:

- Demonstração/local: Airflow + PostgreSQL + Grafana em Docker Compose.
- Produção econômica em EC2 micro: runner Python leve + PostgreSQL local em
  Docker + agendamento por systemd. Airflow e Grafana não ficam consumindo os
  1 GiB de memória da instância 24/7.

## Arquitetura

~~~text
                              HTTPS
+-------------------+     +----------------------------+
| NASA NEO API      | --> | Extract                    |
| api.nasa.gov      |     | JSON bruto por data        |
+-------------------+     +-------------+--------------+
                                             |
                                             v
                               +-------------------------+
                               | Transform               |
                               | normaliza, valida,      |
                               | filtra hazard/Atlas/3I  |
                               +-----------+-------------+
                                           |
                         +-----------------+-----------------+
                         |                                   |
                         v                                   v
          +----------------------------+      +----------------------------+
          | Storage de artefatos       |      | PostgreSQL                  |
          | JSON bruto + CSV tratado   |      | asteroides_monitoria        |
          | retenção automática 90 d   |      | UPSERT por id + data        |
          +----------------------------+      +-------------+--------------+
                                                             |
                                                             v
                                              +----------------------------+
                                              | Grafana opcional            |
                                              | dashboard provisionado      |
                                              +----------------------------+
~~~

## Boas práticas demonstradas

- Extração HTTP com timeout e erro explícito.
- Separação entre dados brutos e tratados, com retenção configurável.
- Transformação determinística e filtros de negócio testáveis.
- UPSERT idempotente no PostgreSQL por identificador e data.
- Segredos fora do Git e entregues somente aos processos que precisam deles.
- Container do ETL executando sem root; Docker é acionado por systemd root
  controlado, sem adicionar o usuário da aplicação ao grupo `docker`.
- Portas de UI limitadas ao loopback, SSH limitado a um IP `/32`, IMDSv2 e
  role SSM no Terraform.
- Reinício após falha, timer persistente após reboot e rotação de logs.

## Pré-requisitos locais

- Python 3.11
- Docker Desktop com Docker Compose v2
- Uma chave da API NASA em [api.nasa.gov](https://api.nasa.gov/)

No PowerShell:

~~~powershell
Copy-Item .env.example .env
py -3.11 -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install --upgrade pip
pip install --constraint https://raw.githubusercontent.com/apache/airflow/constraints-2.9.0/constraints-3.11.txt -r requirements.txt
pytest
~~~

Preencha o `.env`, que é ignorado pelo Git. Gere valores sem caracteres que
quebrem a URL do PostgreSQL:

~~~powershell
python -c "import secrets; print(secrets.token_hex(24))"
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
python -c "import secrets; print(secrets.token_urlsafe(48))"
~~~

Use o primeiro valor como `POSTGRES_PASSWORD`, o segundo como
`AIRFLOW_FERNET_KEY` e o terceiro como senha/chave web. Não use `DEMO_KEY` ou
os valores de exemplo em uma demonstração pública.

## Demonstração local com Airflow

Suba a stack local:

~~~powershell
docker compose up -d --build
docker compose ps
docker compose logs -f airflow-init airflow-scheduler
~~~

`airflow-init` migra o banco, cria a conexão HTTP da NASA e cria o usuário
Airflow somente quando ele ainda não existe. As UIs ficam no loopback:

| Serviço | Endereço | Credenciais |
|---|---|---|
| Airflow | http://127.0.0.1:8080 | `AIRFLOW_ADMIN_USER` e `AIRFLOW_ADMIN_PASSWORD` |
| Grafana opcional | http://127.0.0.1:3001 | `GRAFANA_ADMIN_USER` e `GRAFANA_ADMIN_PASSWORD` |

Para subir Grafana e provisionar automaticamente o datasource PostgreSQL e o
dashboard:

~~~powershell
docker compose --profile observability up -d grafana
~~~

O dashboard é lido de `dashboards/grafana/provisioning_template.json`; os
arquivos YAML em `dashboards/grafana/provisioning/` configuram o datasource e
o provider. A senha do banco não entra no JSON nem no Git.

### Executar o runner leve localmente

Não execute `python scripts/run_etl.py` diretamente no Windows usando
`POSTGRES_HOST=postgres`: esse nome só existe na rede Docker. Use o perfil
`runner`, que compartilha a rede do Compose:

~~~powershell
docker compose up -d postgres
docker compose --profile runner run --rm runner
docker compose logs postgres
~~~

Para rodar o script Python direto, configure um PostgreSQL externo acessível
pelo host e ajuste `POSTGRES_HOST` no ambiente explicitamente.

## Antes de gastar na AWS: verificar conta, plano e credenciais

As regras do Free Tier mudaram. Antes de criar qualquer recurso:

1. Abra **AWS Billing and Cost Management → Free Tier** e confira o consumo
   por serviço e região.
2. Abra **Billing and Cost Management → Credits** e confira o saldo e a data
   de expiração de cada crédito.
3. Na página inicial do Console, confira o widget **Cost and Usage** para
   status do plano, saldo e dias restantes.
4. Em **Billing preferences**, ative alertas de Free Tier quando aplicável e
   crie um **AWS Budget** de baixo valor com alerta por e-mail.
5. Com AWS CLI autenticado, confirme a identidade antes de usar Terraform:

~~~bash
aws sts get-caller-identity
aws freetier get-account-plan-state --output table
~~~

Se `aws sts get-caller-identity` retornar `InvalidClientTokenId`, pare e
renove/remova as credenciais inválidas. Nunca coloque credenciais AWS em
`.env`, user-data ou outputs Terraform.

| Data de criação da conta | Regra EC2 a confirmar no Console |
|---|---|
| Antes de 15/07/2025 | Free Tier legado de 12 meses; `t2.micro` e `t3.micro` podem ser elegíveis enquanto o prazo existir. |
| Em/após 15/07/2025 | Free Plan baseado em créditos, com duração de até 6 meses ou até os créditos acabarem; prefira `t3.micro` x86_64 quando aparecer como elegível. |

Não crie outra conta supondo que isso renova a franquia: clientes que já
tiveram conta não são automaticamente elegíveis a um novo Free Plan/crédito.
Após a expiração, instância ligada, IPv4 público, EBS, snapshots e Elastic IPs
podem gerar cobrança. Um Budget alerta; ele não interrompe recursos.

Fontes oficiais: [uso EC2 no Free Tier](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html),
[rastreamento de uso](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/tracking-free-tier-usage.html),
[estado do plano pelo CLI](https://docs.aws.amazon.com/cli/latest/reference/freetier/get-account-plan-state.html),
[FAQ do Free Tier](https://aws.amazon.com/free/free-tier-faqs/) e
[preço de IPv4 público](https://aws.amazon.com/vpc/pricing/).

## Criar a EC2 pelo Console

O roteiro usa Ubuntu LTS x86_64 e `t3.micro`. Escolha `t2.micro` somente se o
Console confirmar a elegibilidade da sua conta legada.

1. Em **EC2 → Instances → Launch instances**, defina o nome `nasa-etl-prod`.
2. Escolha **Ubuntu Server LTS** marcado como elegível, evitando AMIs do
   Marketplace que cobrem software adicional.
3. Escolha `t3.micro` e selecione **Standard** em CPU credits, não Unlimited.
4. Crie um Key Pair ED25519/RSA e baixe o `.pem` uma única vez. Guarde-o fora
   do repositório.
5. Crie o Security Group conforme a tabela abaixo.
6. Use volume raiz `gp3` pequeno, criptografado e com exclusão ao terminar a
   instância. EBS e snapshots podem cobrar mesmo com a instância parada.
7. Em **Advanced details → IAM instance profile**, associe uma role com
   `AmazonSSMManagedInstanceCore` se quiser usar Session Manager.
8. Em **Advanced details → User data**, cole
   `deploy/ec2/user-data.sh`. Antes, troque `APP_REF="main"` por uma tag
   publicada, por exemplo `APP_REF="v1.0.0"`.
9. Lance a instância, aguarde os checks `2/2` e consulte
   `/var/log/cloud-init-output.log` e `/var/log/nasa-etl-bootstrap.log`.

| Entrada | Porta | Origem segura |
|---|---:|---|
| SSH / Remote-SSH | TCP 22 | somente o seu IP público em `/32` |
| Airflow temporário | TCP 8080 | nenhuma por padrão; se inevitável, apenas seu IP em `/32` |
| Grafana temporário | TCP 3001 | nenhuma por padrão; se inevitável, apenas seu IP em `/32` |
| PostgreSQL | TCP 5432 | nunca pública; somente a rede Docker local deste projeto |

O runtime de produção não publica API web, portanto basta a porta 22. Para ver
UIs use túnel SSH, não `0.0.0.0/0`. Referências: [Launch Wizard](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-launch-instance-wizard.html),
[Security Groups](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/creating-security-group.html) e
[EC2 user-data](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html).

O user-data instala Python, Node.js, Docker, Docker Compose, Git e ferramentas
de build. Ele não contém a chave NASA, token GitHub, senha PostgreSQL ou
credencial AWS. User-data roda como root apenas no primeiro boot; não o trate
como armazenamento de segredos.

## Alternativa reproduzível: Terraform

`infra/ec2` cria somente a EC2, o Security Group mínimo e a role SSM. Ele não
cria access keys estáticas, RDS ou S3.

~~~powershell
Copy-Item infra/ec2/terraform.tfvars.example infra/ec2/terraform.tfvars
# Edite key_pair_name, admin_cidr e repository_ref antes de continuar.
terraform -chdir=infra/ec2 init
terraform -chdir=infra/ec2 plan
terraform -chdir=infra/ec2 apply
terraform -chdir=infra/ec2 output
~~~

Use um `repository_ref` imutável depois do merge/release, por exemplo
`repository_ref = "v1.0.0"`. O módulo aplica IMDSv2, disco criptografado,
créditos CPU `standard`, portas de dashboard fechadas e SSH somente em `/32`.
Revise o plano antes de `apply` e execute `terraform destroy` ao encerrar o
ambiente.

Existe também `infra/terraform`, o módulo legado opcional de S3/RDS. Ele foi
endurecido para RDS privado e sem IAM access key, mas não é necessário para a
EC2 micro. Antes de qualquer `apply` nele, faça `terraform plan`, confirme os
recursos já existentes e escolha explicitamente como conectar o Security Group
da EC2 ao banco privado.

## Injetar o segredo na EC2 e operar 24/7

Depois do boot, conecte-se por SSH e crie o segredo fora do repositório:

~~~bash
ssh -i ~/.ssh/nasa-etl.pem ubuntu@IP_PUBLICO
sudoedit /etc/nasa-etl/nasa-etl.env
~~~

Conteúdo mínimo:

~~~dotenv
TZ=America/Manaus
LOG_LEVEL=INFO
NASA_API_KEY=substitua_pela_sua_chave
NASA_API_BASE=https://api.nasa.gov
NASA_API_RESOURCE=neo/rest/v1/feed
POSTGRES_USER=nasa_app
POSTGRES_PASSWORD=gere_um_valor_hex_aleatorio
POSTGRES_DB=nasa_etl
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
DATA_RETENTION_DAYS=90
~~~

Proteja o arquivo e faça a primeira execução manual:

~~~bash
sudo chown root:root /etc/nasa-etl/nasa-etl.env
sudo chmod 600 /etc/nasa-etl/nasa-etl.env
sudo systemctl start nasa-etl.service
sudo systemctl status nasa-etl.service --no-pager
sudo journalctl -u nasa-etl.service -n 100 --no-pager
sudo systemctl enable --now nasa-etl.timer
systemctl list-timers nasa-etl.timer
~~~

O timer roda todos os dias às `02:15 UTC`, com atraso aleatório de até dez
minutos. `Persistent=true` recupera uma execução perdida depois de reboot;
`Restart=on-failure` tenta novamente após cinco minutos. O JSON bruto e CSV
tratado acima de 90 dias são removidos, o journal fica limitado a 200 MiB e os
logs Docker a três arquivos de 10 MiB por container. O PostgreSQL fica no
volume Docker nomeado `nasa-etl-runtime_postgres_data`, preservado entre
reinícios; só remova esse volume quando quiser apagar deliberadamente o banco.

Para atualizar uma instância já existente para uma nova tag publicada:

~~~bash
sudo systemctl stop nasa-etl.timer
sudo -u nasaetl git -C /opt/nasa-etl fetch --tags --force origin
sudo -u nasaetl git -C /opt/nasa-etl checkout --detach v1.0.1
sudo docker build -t nasa-etl-runtime:local -f /opt/nasa-etl/Dockerfile.runtime /opt/nasa-etl
sudo install -m 0644 /opt/nasa-etl/deploy/systemd/nasa-etl-postgres.service /etc/systemd/system/nasa-etl-postgres.service
sudo install -m 0644 /opt/nasa-etl/deploy/systemd/nasa-etl.service /etc/systemd/system/nasa-etl.service
sudo install -m 0644 /opt/nasa-etl/deploy/systemd/nasa-etl.timer /etc/systemd/system/nasa-etl.timer
sudo systemctl daemon-reload
sudo systemctl enable --now nasa-etl.timer
sudo systemctl start nasa-etl.service
~~~

## VS Code Remote - SSH

1. Instale as extensões **Remote - SSH** e **Python** no VS Code local.
2. Crie ou edite `C:/Users/SEU_USUARIO/.ssh/config`:

~~~sshconfig
Host nasa-etl-ec2
  HostName IP_PUBLICO_DA_EC2
  User ubuntu
  IdentityFile C:/Users/SEU_USUARIO/.ssh/nasa-etl.pem
  IdentitiesOnly yes
  ServerAliveInterval 60
  ServerAliveCountMax 3
~~~

3. Execute **Remote-SSH: Connect to Host...**, selecione `nasa-etl-ec2` e abra
   `/opt/nasa-etl`.
4. Instale a extensão Python no host remoto e use breakpoints em
   `etl/pipeline.py` ao executar os testes de transformação. Para isso, crie
   uma venv de depuração sem Airflow:

~~~bash
cd /opt/nasa-etl
python3 -m venv .venv-debug
.venv-debug/bin/pip install -r requirements.runtime.txt pytest
.venv-debug/bin/python -m pytest tests/test_pipeline.py -q
~~~

5. Para depurar a execução real, rode o mesmo container usado pelo timer e
   acompanhe seus logs:

~~~bash
sudo docker compose --env-file /etc/nasa-etl/nasa-etl.env -f /opt/nasa-etl/deploy/compose/docker-compose.ec2.yml run --rm --no-deps nasa-etl --date 2026-08-20
sudo journalctl -u nasa-etl.service -f
~~~

Se subir a demonstração com Airflow/Grafana na EC2, mantenha as portas em
`127.0.0.1` e crie um túnel:

~~~bash
ssh -L 8080:127.0.0.1:8080 -L 3001:127.0.0.1:3001 -i ~/.ssh/nasa-etl.pem ubuntu@IP_PUBLICO
~~~

Abra então as interfaces no navegador local. Não é necessário liberar 8080 ou
3001 no Security Group.

## Publicação para portfólio no GitHub

Use uma branch e selecione somente os arquivos revisados. Nunca use `git add .`:

~~~bash
git switch -c feat/ec2-runtime
git add -- README.md .gitignore .dockerignore .env.example Dockerfile Dockerfile.runtime docker-compose.yml requirements.txt requirements.airflow.txt requirements.runtime.txt
git add -- etl scripts tests deploy infra/ec2 infra/terraform dashboards/grafana .github/workflows/ci.yml pytest.ini
git commit -m "feat: add secure EC2 runtime and deployment guide"
git push -u origin feat/ec2-runtime
gh pr create --draft --base main --head feat/ec2-runtime --title "feat: secure EC2 runtime and deployment guide"
~~~

Revise o Pull Request, faça o merge e crie uma tag antes de apontar uma EC2
para a nova versão. `.gitignore` bloqueia `.env`, PEM/PPK, chaves, state e
artefatos gerados. Ainda assim, confirme com `git status` que nenhum segredo
foi selecionado antes do commit.

## Validação

~~~powershell
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example -f deploy/compose/docker-compose.ec2.yml config --quiet
terraform -chdir=infra/ec2 fmt -check
terraform -chdir=infra/ec2 validate
~~~

Em ambiente Linux/Docker, execute também:

~~~bash
docker build --tag nasa-etl-runtime:test --file Dockerfile.runtime .
docker run --rm nasa-etl-runtime:test --help
~~~

## Encerramento seguro

Ao terminar entrevistas ou demonstrações, pare/termine a EC2 e destrua apenas
o módulo que você realmente criou:

~~~bash
terraform -chdir=infra/ec2 destroy
~~~

Confira no Billing e no Console se não ficaram volumes EBS, snapshots, Elastic
IPs ou recursos do módulo legado. Parar uma instância não elimina cobrança de
EBS nem de alguns IPs.

## Licença

Distribuído sob a [Apache License 2.0](LICENSE).
