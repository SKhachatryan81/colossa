resource "google_storage_bucket" "bucket_backup" {
  name = "bucket-backup"
  location = var.region

  public_access_prevention    = "enforced"
  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 30
      matches_prefix = ["raw/"]
    }
    action {
      type          = "SetStorageClass"
        storage_class = "ARCHIVE"
    }
  }
}

resource "google_storage_bucket_iam_member" "vm_admin" {
  bucket = google_storage_bucket.bucket_backup.id
  role = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_account}"
}