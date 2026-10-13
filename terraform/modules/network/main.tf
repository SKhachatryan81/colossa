resource "google_compute_network" "network" {
  name = "network"
  project = var.project
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name = "subnet"
  ip_cidr_range = "10.0.0.0/24"
  network = google_compute_network.network.id
}

resource "google_compute_firewall" "default" {
  name = "default-firewall"
  project = var.project
  network = google_compute_network.network.id
  target_tags = ["default"]

  allow {
    protocol = "tcp"
    ports = ["22"]
  }
  source_ranges = ["35.235.240.0/20"]
}

resource "google_compute_router" "router" {
  name = "router"
  project = var.project
  region = var.region
  network = google_compute_network.network.id
}

resource "google_compute_router_nat" "nat" {
  name = "nat"
  project = var.project
  region = var.region
  router = google_compute_router.router.id
  nat_ip_allocate_option = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}