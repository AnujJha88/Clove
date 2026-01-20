# AgentOS GCP Outputs

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

output "project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "ssh_command" {
  description = "SSH command to connect"
  value       = "gcloud compute ssh ${google_compute_instance.agentos.name} --zone=${var.zone}"
}
