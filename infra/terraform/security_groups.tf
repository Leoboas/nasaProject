data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Subnet group usando subnets do VPC default. O RDS continua privado.
resource "aws_db_subnet_group" "default" {
  name       = "${var.project_name}-subnets"
  subnet_ids = data.aws_subnets.default.ids

  tags = merge(local.common_tags, { Component = "rds-subnet-group" })
}

# Não existe regra pública. Libere somente Security Groups de workloads
# autorizados (por exemplo, o output security_group_id de infra/ec2).
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Private PostgreSQL access for approved clients"
  vpc_id      = data.aws_vpc.default.id

  dynamic "ingress" {
    for_each = var.rds_client_security_group_ids

    content {
      description     = "PostgreSQL from approved workload SG"
      from_port       = 5432
      to_port         = 5432
      protocol        = "tcp"
      security_groups = [ingress.value]
    }
  }

  # Use somente para migração/debug controlado; prefira o SG acima.
  dynamic "ingress" {
    for_each = var.rds_admin_cidrs

    content {
      description = "Temporary PostgreSQL admin access"
      from_port   = 5432
      to_port     = 5432
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Component = "rds-security-group" })
}
