# Terraform: EC2 leve para o NASA ETL

Este módulo cria somente uma EC2 Ubuntu, Security Group mínimo e uma role para
AWS Systems Manager. Ele não cria access keys estáticas, RDS ou S3.

Antes de aplicar:

~~~bash
cd infra/ec2
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
~~~

Edite `key_pair_name`, `admin_cidr` e `repository_ref` no arquivo
`terraform.tfvars`. `admin_cidr` aceita exclusivamente um IPv4 individual em
`/32`; `0.0.0.0/0` é rejeitado. Para o deploy de entrevista, publique uma tag
e use-a como `repository_ref`, por exemplo `v1.0.0`.

O user-data instala Docker, Docker Compose, Python, Node.js e Git, faz checkout
da referência configurada e habilita o timer do systemd. Depois do boot, injete
o segredo manualmente em `/etc/nasa-etl/nasa-etl.env`, com permissão `600`,
conforme o README principal. Nenhum segredo deve entrar em Terraform ou
user-data.

O módulo aplica IMDSv2, volume gp3 criptografado, CPU credits `standard` e
SSH limitado ao CIDR administrativo. Verifique elegibilidade/custos no Billing
e revise o plano antes do apply.

Para remover apenas os recursos deste módulo:

~~~bash
terraform destroy
~~~

Depois, confira no Console se não ficaram volumes EBS, snapshots, Elastic IPs
ou recursos de outros módulos.
