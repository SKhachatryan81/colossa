output "network" {
  value = google_compute_network.network.id
}

output "subnet" {
  value       = google_compute_subnetwork.subnet.id
}