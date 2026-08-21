variable "aws_region" {
  description = "AWS region where the EC2 will be created."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix used in resource names and tags."
  type        = string
  default     = "nasa-etl"
}

variable "environment" {
  description = "Instance environment."
  type        = string
  default     = "production"
}

variable "instance_type" {
  description = "Use t3.micro for a current Free Plan; t2.micro is legacy only."
  type        = string
  default     = "t3.micro"
}

variable "key_pair_name" {
  description = "Name of an existing EC2 Key Pair; never put its PEM file here."
  type        = string
}

variable "admin_cidr" {
  description = "Administrator public IP, for example 203.0.113.10/32."
  type        = string

  validation {
    condition = can(cidrhost(var.admin_cidr, 0)) && can(
      regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/32$", var.admin_cidr)
    )
    error_message = "admin_cidr must be one IPv4 address in x.x.x.x/32 format."
  }
}

variable "root_volume_gb" {
  description = "Size of the encrypted gp3 root volume."
  type        = number
  default     = 12

  validation {
    condition     = var.root_volume_gb >= 8 && var.root_volume_gb <= 30
    error_message = "Use between 8 and 30 GiB for this cost-conscious environment."
  }
}

variable "repository_url" {
  description = "Public Git repository cloned during bootstrap."
  type        = string
  default     = "https://github.com/Leoboas/nasaProject.git"

  validation {
    condition     = can(regex("^https://[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9._-]+)+\\.git$", var.repository_url))
    error_message = "repository_url must be a safe HTTPS Git URL ending in .git."
  }
}

variable "repository_ref" {
  description = "Git tag, branch, or commit SHA checked out by the bootstrap. Prefer a release tag."
  type        = string
  default     = "main"

  validation {
    condition     = can(regex("^[0-9A-Za-z._/-]{1,128}$", var.repository_ref))
    error_message = "repository_ref may contain only letters, digits, dot, underscore, slash, and hyphen."
  }
}
