locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    AccountType = "aws-education"
  }
}

resource "aws_instance" "nasa_etl" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [var.security_group_id]
  key_name                    = var.key_pair_name
  iam_instance_profile        = var.instance_profile_name
  associate_public_ip_address = true

  user_data = replace(
    replace(
      file("${path.module}/../../deploy/ec2/user-data.sh"),
      "APP_REPOSITORY_URL=\"https://github.com/Leoboas/nasaProject.git\"",
      "APP_REPOSITORY_URL=\"${var.repository_url}\"",
    ),
    "APP_REF=\"main\"",
    "APP_REF=\"${var.repository_ref}\"",
  )

  user_data_replace_on_change = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    delete_on_termination = true
  }

  credit_specification {
    cpu_credits = "standard"
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-education"
  })
}
