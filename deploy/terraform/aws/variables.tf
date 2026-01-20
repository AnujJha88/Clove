# AgentOS AWS Variables
# Override these in terraform.tfvars or via -var flags

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
  description = "Subnet ID (optional)"
  type        = string
  default     = ""
}

variable "security_group_id" {
  description = "Security group ID (optional)"
  type        = string
  default     = ""
}

variable "ami_id" {
  description = "AMI ID (optional, uses latest Ubuntu if not specified)"
  type        = string
  default     = ""
}
