variable "aws_region" {
  description = "Região AWS"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Nome base do projeto (usado em recursos)"
  type        = string
  default     = "nasa-etl-demo"
}

variable "environment" {
  description = "Ambiente (ex.: dev, prod)"
  type        = string
  default     = "dev"
}

variable "cost_control" {
  description = "Indicador de controle de custo"
  type        = string
  default     = "free-tier"
}

variable "managed_by" {
  description = "Origem da automação"
  type        = string
  default     = "terraform"
}

variable "bucket_name" {
  description = "Nome do bucket S3 (único globalmente)"
  type        = string
  default     = "nasa-etl-demo"
}

variable "lifecycle_days" {
  description = "Dias para expirar objetos no S3"
  type        = number
  default     = 30
}

variable "db_name" {
  description = "Nome do banco Postgres"
  type        = string
  default     = "nasa_etl"
}

variable "db_username" {
  description = "Usuário mestre do Postgres"
  type        = string
  default     = "nasa_admin"
}

variable "db_password" {
  description = "Senha do Postgres (sensível)"
  type        = string
  sensitive   = true
}

variable "db_port" {
  description = "Porta do Postgres"
  type        = number
  default     = 5432
}

variable "db_engine_version" {
  description = "Versão do Postgres (14.x elegível Free Tier)"
  type        = string
  default     = "14.13"
}

variable "db_instance_class" {
  description = "Classe da instância RDS (Free Tier)"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Armazenamento alocado (GB) - Free Tier máximo 20GB"
  type        = number
  default     = 20
}

variable "alert_email" {
  description = "Email para notificações (SNS/Budget)"
  type        = string
}

variable "s3_storage_threshold_gb" {
  description = "Limite de alarme para tamanho do bucket (GB)"
  type        = number
  default     = 4.5
}

variable "s3_put_requests_threshold" {
  description = "Limite de alarme para número de objetos/PUT aproximado"
  type        = number
  default     = 1800
}

variable "rds_free_storage_threshold_gb" {
  description = "Limite de alarme para espaço livre no RDS (GB)"
  type        = number
  default     = 2
}

variable "budget_limit" {
  description = "Limite mensal do budget (USD)"
  type        = number
  default     = 1.0
}
