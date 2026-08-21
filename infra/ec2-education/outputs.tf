output "instance_id" {
  value = aws_instance.nasa_etl.id
}

output "public_ip" {
  value = aws_instance.nasa_etl.public_ip
}

output "ssh_command" {
  value = "ssh -i ./nasa-key.pem ubuntu@${aws_instance.nasa_etl.public_ip}"
}
