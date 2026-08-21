output "instance_id" {
  value       = aws_instance.nasa_etl.id
  description = "ID da instância EC2."
}

output "public_ip" {
  value       = aws_instance.nasa_etl.public_ip
  description = "IP público para SSH/Remote-SSH."
}

output "security_group_id" {
  value       = aws_security_group.ec2.id
  description = "Security Group da instância."
}

output "ssh_command" {
  value       = "ssh -i ~/.ssh/SEU_KEY.pem ubuntu@${aws_instance.nasa_etl.public_ip}"
  description = "Ajuste o caminho da chave antes de executar."
}
