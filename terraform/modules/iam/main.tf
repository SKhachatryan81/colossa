resource "google_service_account" "vm_sa" {
  account_id   = "vm-sa"
  display_name = "SM service account"
}

locals {
  vm_roles = [
    "roles/iap.tunnelResourceAccessor",
    "roles/compute.osLogin"
  ]
}

resource "google_project_iam_member" "owner_access" {
  project = var.project
  
  for_each = toset(local.vm_roles)
  role = each.value
  member = "serviceAccount:${var.owner_account}"
}