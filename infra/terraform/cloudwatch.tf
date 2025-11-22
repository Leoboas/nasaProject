locals {
  s3_storage_threshold_bytes       = var.s3_storage_threshold_gb * 1024 * 1024 * 1024
  rds_free_storage_threshold_bytes = var.rds_free_storage_threshold_gb * 1024 * 1024 * 1024
}

# SNS para alertas
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"
  tags = merge(local.common_tags, { Component = "sns-alerts" })
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Alarme: uso de armazenamento S3 (90% do limite de 5 GB)
resource "aws_cloudwatch_metric_alarm" "s3_storage" {
  alarm_name          = "${var.project_name}-s3-storage-usage"
  alarm_description   = "Alertar quando o bucket S3 atingir ~90% do Free Tier (4.5 GB)."
  namespace           = "AWS/S3"
  metric_name         = "BucketSizeBytes"
  statistic           = "Average"
  period              = 86400
  evaluation_periods  = 1
  threshold           = local.s3_storage_threshold_bytes
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    BucketName = aws_s3_bucket.data_lake.bucket
    StorageType = "StandardStorage"
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
  tags          = merge(local.common_tags, { Component = "cw-alarm-s3-storage" })
}

# Alarme: numero de objetos (proxy para requisicoes PUT ~ Free Tier)
resource "aws_cloudwatch_metric_alarm" "s3_put_requests" {
  alarm_name          = "${var.project_name}-s3-put-requests"
  alarm_description   = "Alertar quando o numero de objetos se aproximar do limite de requisicoes PUT do Free Tier."
  namespace           = "AWS/S3"
  metric_name         = "NumberOfObjects"
  statistic           = "Average"
  period              = 86400
  evaluation_periods  = 1
  threshold           = var.s3_put_requests_threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    BucketName = aws_s3_bucket.data_lake.bucket
    StorageType = "AllStorageTypes"
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
  tags          = merge(local.common_tags, { Component = "cw-alarm-s3-requests" })
}

# Alarme: espaco livre em RDS (alerta quando restar < 2 GB)
resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "${var.project_name}-rds-storage"
  alarm_description   = "Alertar quando o RDS tiver menos de 2GB livres (~18GB usados do Free Tier)."
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 1
  threshold           = local.rds_free_storage_threshold_bytes
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
  tags          = merge(local.common_tags, { Component = "cw-alarm-rds-storage" })
}
