# AgentOS Kernel - AWS EC2 Deployment
#
# This Terraform module provisions an EC2 instance running AgentOS kernel.
#
# Usage:
#   terraform init
#   terraform apply -var="machine_id=my-kernel" -var="machine_token=xxx"

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Variables
variable "machine_id" {
  description = "Unique machine ID for this kernel"
  type        = string
}

variable "machine_token" {
  description = "Authentication token for relay server"
  type        = string
  sensitive   = true
}

variable "relay_url" {
  description = "WebSocket URL of the relay server"
  type        = string
  default     = "wss://relay.agentos.example.com"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "instance_name" {
  description = "Name tag for the EC2 instance"
  type        = string
  default     = "agentos-kernel"
}

variable "key_name" {
  description = "SSH key pair name"
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "Subnet ID (optional, uses default VPC if not specified)"
  type        = string
  default     = ""
}

variable "security_group_id" {
  description = "Security group ID (optional, creates new one if not specified)"
  type        = string
  default     = ""
}

variable "ami_id" {
  description = "AMI ID (optional, uses latest Ubuntu 22.04 if not specified)"
  type        = string
  default     = ""
}

# Provider
provider "aws" {
  region = var.region
}

# Data sources
data "aws_ami" "ubuntu" {
  count       = var.ami_id == "" ? 1 : 0
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Security Group (if not provided)
resource "aws_security_group" "agentos" {
  count       = var.security_group_id == "" ? 1 : 0
  name        = "${var.instance_name}-sg"
  description = "Security group for AgentOS kernel"
  vpc_id      = data.aws_vpc.default.id

  # SSH access
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "SSH access"
  }

  # All outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound"
  }

  tags = {
    Name    = "${var.instance_name}-sg"
    Project = "AgentOS"
  }
}

# IAM Role for EC2
resource "aws_iam_role" "agentos" {
  name = "${var.instance_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

  tags = {
    Name    = "${var.instance_name}-role"
    Project = "AgentOS"
  }
}

resource "aws_iam_instance_profile" "agentos" {
  name = "${var.instance_name}-profile"
  role = aws_iam_role.agentos.name
}

# EC2 Instance
resource "aws_instance" "agentos" {
  ami                    = var.ami_id != "" ? var.ami_id : data.aws_ami.ubuntu[0].id
  instance_type          = var.instance_type
  key_name               = var.key_name != "" ? var.key_name : null
  subnet_id              = var.subnet_id != "" ? var.subnet_id : data.aws_subnets.default.ids[0]
  vpc_security_group_ids = var.security_group_id != "" ? [var.security_group_id] : [aws_security_group.agentos[0].id]
  iam_instance_profile   = aws_iam_instance_profile.agentos.name

  user_data = templatefile("${path.module}/cloud-init.yaml", {
    machine_id    = var.machine_id
    machine_token = var.machine_token
    relay_url     = var.relay_url
  })

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  tags = {
    Name       = var.instance_name
    Project    = "AgentOS"
    MachineID  = var.machine_id
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Outputs
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
