data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Subnet group usando subnets do VPC default (dev/Free Tier)
resource "aws_db_subnet_group" "default" {
  name       = "${var.project_name}-subnets"
  subnet_ids = data.aws_subnets.default.ids

  tags = merge(local.common_tags, { Component = "rds-subnet-group" })
}

# Security Group liberando porta 5432 (dev). Restrinja ao seu IP em prod.
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Acesso ao Postgres RDS (porta 5432) - ambiente dev"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Postgres"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Component = "rds-security-group" })
}
