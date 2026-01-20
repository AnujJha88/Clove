# AgentOS Kernel - GCP Compute Engine Deployment
#
# This Terraform module provisions a Compute Engine instance running AgentOS kernel.
#
# Usage:
#   terraform init
#   terraform apply -var="project_id=my-project" -var="machine_id=my-kernel" -var="machine_token=xxx"

terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Variables
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

# Provider
provider "google" {
  project = var.project_id
  region  = regex("^([a-z]+-[a-z0-9]+)", var.zone)[0]
  zone    = var.zone
}

# Data source for latest Ubuntu image
data "google_compute_image" "ubuntu" {
  family  = "ubuntu-2204-lts"
  project = "ubuntu-os-cloud"
}

# Firewall rule for SSH
resource "google_compute_firewall" "agentos_ssh" {
  name    = "${var.instance_name}-allow-ssh"
  network = var.network

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["agentos-kernel"]
}

# Service Account
resource "google_service_account" "agentos" {
  account_id   = "${var.instance_name}-sa"
  display_name = "AgentOS Kernel Service Account"
}

# Compute Engine Instance
resource "google_compute_instance" "agentos" {
  name         = var.instance_name
  machine_type = var.machine_type
  zone         = var.zone

  tags = ["agentos-kernel"]

  boot_disk {
    initialize_params {
      image = data.google_compute_image.ubuntu.self_link
      size  = 20
      type  = "pd-ssd"
    }
  }

  network_interface {
    network    = var.network
    subnetwork = var.subnetwork != "" ? var.subnetwork : null

    access_config {
      # Ephemeral public IP
    }
  }

  metadata = {
    user-data = templatefile("${path.module}/cloud-init.yaml", {
      machine_id    = var.machine_id
      machine_token = var.machine_token
      relay_url     = var.relay_url
    })
  }

  service_account {
    email  = google_service_account.agentos.email
    scopes = ["cloud-platform"]
  }

  labels = {
    project    = "agentos"
    machine_id = replace(var.machine_id, "/[^a-z0-9-]/", "-")
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Outputs
output "instance_name" {
  description = "Compute Engine instance name"
  value       = google_compute_instance.agentos.name
}

output "external_ip" {
  description = "External IP address"
  value       = google_compute_instance.agentos.network_interface[0].access_config[0].nat_ip
}

output "internal_ip" {
  description = "Internal IP address"
  value       = google_compute_instance.agentos.network_interface[0].network_ip
}

output "machine_id" {
  description = "AgentOS machine ID"
  value       = var.machine_id
}

output "zone" {
  description = "GCP zone"
  value       = var.zone
}

output "ssh_command" {
  description = "SSH command to connect"
  value       = "gcloud compute ssh ${google_compute_instance.agentos.name} --zone=${var.zone}"
}
