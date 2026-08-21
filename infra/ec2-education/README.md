# EC2 Education

Esta variante não cria IAM Role, Instance Profile, VPC, subnet ou Security Group.
Ela usa IDs previamente fornecidos pela AWS Academy/AWS Educate e é adequada para
contas com SCPs restritivas.

O módulo cria uma nova instância. A instância existente `i-0bbb240e6e5eba9b7`
deve ser validada por SSH e não deve ser recriada sem uma decisão explícita.

Preencha `terraform.tfvars` com AMI, subnet e Security Group existentes antes de
executar `terraform plan`.
