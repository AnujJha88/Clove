# AgentOS AWS Outputs

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.agentos.id
}

output "public_ip" {
  description = "Public IP address"
  value       = aws_instance.agentos.public_ip
}

output "private_ip" {
  description = "Private IP address"
  value       = aws_instance.agentos.private_ip
}

output "machine_id" {
  description = "AgentOS machine ID"
  value       = var.machine_id
}

output "ssh_command" {
  description = "SSH command to connect"
  value       = var.key_name != "" ? "ssh -i ~/.ssh/${var.key_name}.pem ubuntu@${aws_instance.agentos.public_ip}" : "No SSH key configured"
}

output "region" {
  description = "AWS region"
  value       = var.region
}
