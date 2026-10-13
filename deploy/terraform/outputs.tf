output "api_url" {
  value       = local.api_url
  description = "Use as HELIX_API_PROXY_TARGET when building the web image."
}

output "web_url" {
  value = local.web_url
}

output "image_repository" {
  value       = local.repo_url
  description = "Push images as <repository>/api:<tag> and <repository>/web:<tag>."
}

output "cloud_sql_connection_name" {
  value = google_sql_database_instance.main.connection_name
}

output "api_service_account" {
  value = google_service_account.api.email
}

output "github_variables" {
  description = "Set these as variables on the matching GitHub environment."
  value = {
    GCP_PROJECT_ID   = var.project_id
    GCP_REGION       = var.region
    GCP_WIF_PROVIDER = google_iam_workload_identity_pool_provider.github.name
    GCP_DEPLOYER_SA  = google_service_account.deployer.email
    IMAGE_REPOSITORY = local.repo_url
    API_SERVICE      = "${local.prefix}-api"
    WEB_SERVICE      = "${local.prefix}-web"
    HELIX_API_URL    = local.api_url
  }
}
