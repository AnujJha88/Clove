# AgentOS GCP Variables
# Override these in terraform.tfvars or via -var flags

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

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

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "machine_type" {
  description = "Compute Engine machine type"
  type        = string
  default     = "n1-standard-1"
}

variable "instance_name" {
  description = "Name for the Compute Engine instance"
  type        = string
  default     = "agentos-kernel"
}

variable "network" {
  description = "VPC network name"
  type        = string
  default     = "default"
}

variable "subnetwork" {
  description = "Subnetwork name (optional)"
  type        = string
  default     = ""
}
