variable "aws_region" {
  type    = string
  default = "us-east-2"
}

variable "project_name" {
  type    = string
  default = "nasa-etl"
}

variable "environment" {
  type    = string
  default = "education"
}

variable "ami_id" {
  description = "Ubuntu AMI ID supplied by the education account/region."
  type        = string
}

variable "subnet_id" {
  description = "Existing subnet ID in the supplied VPC."
  type        = string
}

variable "security_group_id" {
  description = "Existing security group ID; no SG is created by this module."
  type        = string
}

variable "key_pair_name" {
  type = string
}

variable "instance_profile_name" {
  description = "Optional pre-approved instance profile."
  type        = string
  default     = null
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "root_volume_gb" {
  type    = number
  default = 12
}

variable "repository_url" {
  type    = string
  default = "https://github.com/Leoboas/nasaProject.git"
}

variable "repository_ref" {
  type    = string
  default = "v1.0.0"
}
