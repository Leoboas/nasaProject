output "aws_region" {
  value = var.aws_region
}

output "bucket_name" {
  value = aws_s3_bucket.data_lake.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.data_lake.arn
}

output "postgres_endpoint" {
  value = aws_db_instance.postgres.endpoint
}

output "postgres_host" {
  value = aws_db_instance.postgres.address
}

output "postgres_port" {
  value = aws_db_instance.postgres.port
}

output "postgres_database" {
  value = aws_db_instance.postgres.db_name
}

output "postgres_username" {
  value     = aws_db_instance.postgres.username
  sensitive = true
}

output "cloudwatch_alarm_arns" {
  value = [
    aws_cloudwatch_metric_alarm.s3_storage.arn,
    aws_cloudwatch_metric_alarm.s3_put_requests.arn,
    aws_cloudwatch_metric_alarm.rds_storage.arn
  ]
}
