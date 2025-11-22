locals {
  # Tags consistentes para todos os recursos
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    CostControl = var.cost_control
    ManagedBy   = var.managed_by
  }
}

# -------------------------
# S3 Data Lake (Free Tier)
# -------------------------
resource "aws_s3_bucket" "data_lake" {
  bucket        = var.bucket_name
  force_destroy = true # facilita ambientes de dev
  tags          = merge(local.common_tags, { Component = "data-lake" })
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3 (gratuito)
    }
  }
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  versioning_configuration {
    status = "Suspended" # Desabilita versionamento para economizar
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    id     = "expire-objects"
    status = "Enabled"

    expiration {
      days = var.lifecycle_days # Objetos expirados apos 30 dias (Free Tier)
    }

    noncurrent_version_expiration {
      noncurrent_days = 7 # Versoes antigas removidas em 7 dias
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    expired_object_delete_marker = true
  }
}

# -------------------------
# IAM User & Policy minimos
# -------------------------
resource "aws_iam_user" "etl_user" {
  name = "${var.project_name}-user"
  tags = merge(local.common_tags, { Component = "iam" })
}

resource "aws_iam_access_key" "etl_user_key" {
  user = aws_iam_user.etl_user.name
}

data "aws_iam_policy_document" "etl_policy" {
  statement {
    actions = [
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.data_lake.arn
    ]
  }

  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = [
      "${aws_s3_bucket.data_lake.arn}/*"
    ]
  }

  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]
  }

  statement {
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
  }
}

resource "aws_iam_user_policy" "etl_user_policy" {
  name   = "${var.project_name}-policy"
  user   = aws_iam_user.etl_user.name
  policy = data.aws_iam_policy_document.etl_policy.json
}

# -------------------------
# RDS Postgres (Free Tier)
# -------------------------
resource "aws_db_instance" "postgres" {
  identifier                 = "${var.project_name}-postgres"
  engine                     = "postgres"
  engine_version             = var.db_engine_version
  instance_class             = var.db_instance_class
  allocated_storage          = var.db_allocated_storage
  max_allocated_storage      = var.db_allocated_storage
  storage_type               = "gp2"
  db_name                    = var.db_name
  username                   = var.db_username
  password                   = var.db_password
  port                       = var.db_port
  publicly_accessible        = true
  multi_az                   = false
  backup_retention_period    = 0
  delete_automated_backups   = true
  skip_final_snapshot        = true
  deletion_protection        = false
  apply_immediately          = true
  auto_minor_version_upgrade = true

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.default.name

  tags = merge(local.common_tags, { Component = "rds" })
}
