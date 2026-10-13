resource "google_compute_instance" "vm" {
  name = "vm"
  project = var.project
  zone = var.zone
  machine_type = "e2-micro"
  
  network_interface {
    network = var.network
  }

  tags = ["default"]

  boot_disk {
    initialize_params {
      image = "debian-12"
    }
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  metadata_startup_script = file("${path.module}/startup.sh")

  service_account {
    email  = var.service_account
    scopes = ["cloud-platform"]
  }
}

resource "google_compute_disk" "persistant_disk" {
  name = "vm-disk"
  type = "pd-hdd"
  zone = var.zone
  image = "debian-12"
  
  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_attached_disk" "default" {
  disk     = google_compute_disk.persistant_disk.id
  instance = google_compute_instance.vm.id
}
