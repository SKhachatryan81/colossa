terraform {
  required_providers {
    google = {
        source  = "hashicorp/google"
        version = "~> 8.1"
    }
  }
  backend "gcs" {
    bucket = "colossa-terraform-backend"
    prefix = "terraform/state"
  }
}
provider "google" {
  project = "colossa"
}