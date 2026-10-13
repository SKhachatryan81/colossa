resource "google_secret_manager_secret" "secrets" {
  for_each = toset(["github-token", "anthropic-api-key", "reddit-client-id", "reddit-client-secret"])
  secret_id = each.value
  project   = var.project

    replication {
      auto {}
    }
}

resource "google_secret_manager_secret_iam_member" "secret_iam" {
  for_each = google_secret_manager_secret.secrets

  project = var.project
  secret_id = each.value.secret_id
  role = "roles/secretmanager.secretAccessor"
  member = "serviceAccount:${var.service_account}"
}