data "google_project" "this" {}

locals {
  prefix  = "${var.name}-${var.environment}"
  is_prod = var.environment == "production"

  # New-style Cloud Run URLs are deterministic: SERVICE-PROJECTNUMBER.REGION.run.app
  default_api_url = "https://${local.prefix}-api-${data.google_project.this.number}.${var.region}.run.app"
  default_web_url = "https://${local.prefix}-web-${data.google_project.this.number}.${var.region}.run.app"
  api_url         = var.api_url != "" ? var.api_url : local.default_api_url
  web_url         = var.web_url != "" ? var.web_url : (var.web_domain != "" ? "https://${var.web_domain}" : local.default_web_url)

  create_services = var.api_image != "" && var.web_image != ""
  repo_url        = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "aiplatform.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
resource "google_artifact_registry_repository" "images" {
  repository_id = local.prefix
  format        = "DOCKER"
  location      = var.region
  description   = "HelixOS ${var.environment} images"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 20
    }
  }
  cleanup_policy_dry_run = false

  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
resource "google_sql_database_instance" "main" {
  name                = "${local.prefix}-pg"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = local.is_prod

  settings {
    tier              = var.db_tier
    edition           = "ENTERPRISE"
    availability_type = var.db_high_availability ? "REGIONAL" : "ZONAL"
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "21:00" # 02:30 IST
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 14
      }
    }

    # Cloud Run connects through the Cloud SQL connector (unix socket); no
    # authorized networks are opened.
    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    maintenance_window {
      day  = 7
      hour = 21
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "app" {
  name     = "helixos"
  instance = google_sql_database_instance.main.name
}

resource "random_password" "db" {
  length  = 32
  special = false # keeps the connection URL free of characters needing escaping
}

resource "google_sql_user" "app" {
  name     = "helixos"
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}

# ---------------------------------------------------------------------------
# Secrets (values never appear in service definitions, only references)
# ---------------------------------------------------------------------------
resource "google_secret_manager_secret" "database_url" {
  secret_id = "${local.prefix}-database-url"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql+psycopg://${google_sql_user.app.name}:${random_password.db.result}@/${google_sql_database.app.name}?host=/cloudsql/${google_sql_database_instance.main.connection_name}"
}

# The value is added out of band (see docs/DEPLOYMENT.md); Terraform never sees it.
resource "google_secret_manager_secret" "openai_api_key" {
  count     = var.ai_provider == "openai" ? 1 : 0
  secret_id = "${local.prefix}-openai-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------------------
# Runtime identities
# ---------------------------------------------------------------------------
resource "google_service_account" "api" {
  account_id   = "${local.prefix}-api"
  display_name = "HelixOS API (${var.environment})"
}

resource "google_service_account" "web" {
  account_id   = "${local.prefix}-web"
  display_name = "HelixOS web (${var.environment})"
}

resource "google_project_iam_member" "api_cloudsql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_vertex" {
  count   = var.ai_provider == "vertex" ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_openai" {
  count     = var.ai_provider == "openai" ? 1 : 0
  secret_id = google_secret_manager_secret.openai_api_key[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# ---------------------------------------------------------------------------
# API service
# ---------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "api" {
  count               = local.create_services ? 1 : 0
  name                = "${local.prefix}-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = local.is_prod

  template {
    service_account = google_service_account.api.email
    # Long-lived agent streams (SSE) need a generous request timeout.
    timeout = "3600s"

    scaling {
      min_instance_count = var.api_min_instances
      # AI sessions and runs are held in process memory, so a second instance
      # cannot see the first's sessions. Raise only after they are persisted.
      max_instance_count = 1
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }

    containers {
      image = var.api_image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name  = "HELIX_ENV"
        value = var.environment
      }
      env {
        name  = "ALLOWED_ORIGINS"
        value = local.web_url
      }
      dynamic "env" {
        for_each = var.oidc_issuer != "" ? { HELIX_OIDC_ISSUER = var.oidc_issuer, HELIX_OIDC_AUDIENCE = var.oidc_audience } : {}
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name  = "HELIX_AI_PROVIDER"
        value = var.ai_provider
      }
      # Cloud Run's front end is the one trusted proxy: the client address is the
      # rightmost X-Forwarded-For entry (used by rate limiting).
      env {
        name  = "HELIX_TRUSTED_PROXY_HOPS"
        value = "1"
      }
      # Spend control: token prices and caps. Required for a paid provider.
      dynamic "env" {
        for_each = { for k, v in {
          HELIX_AI_PRICE_INPUT_USD_PER_MTOK  = var.ai_price_input_usd_per_mtok
          HELIX_AI_PRICE_OUTPUT_USD_PER_MTOK = var.ai_price_output_usd_per_mtok
          HELIX_AI_BUDGET_GLOBAL_MONTHLY_USD = var.ai_budget_global_monthly_usd
          HELIX_AI_BUDGET_ORG_DAILY_USD      = var.ai_budget_org_daily_usd
          HELIX_AI_BUDGET_ORG_MONTHLY_USD    = var.ai_budget_org_monthly_usd
          HELIX_AI_BUDGET_USER_DAILY_USD     = var.ai_budget_user_daily_usd
        } : k => v if v != "" }
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = var.enable_demo_tokens && !local.is_prod ? [1] : []
        content {
          name  = "HELIX_ENABLE_DEMO_TOKENS"
          value = "1"
        }
      }
      dynamic "env" {
        for_each = var.ai_provider == "vertex" ? [1] : []
        content {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }
      }
      env {
        name = "HELIX_DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }
      dynamic "env" {
        for_each = var.ai_provider == "openai" ? [1] : []
        content {
          name = "HELIX_OPENAI_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.openai_api_key[0].secret_id
              version = "latest"
            }
          }
        }
      }

      # Traffic is only sent once migrations have run and the database answers.
      startup_probe {
        http_get {
          path = "/ready"
        }
        period_seconds    = 5
        timeout_seconds   = 3
        failure_threshold = 24
      }
      liveness_probe {
        http_get {
          path = "/health"
        }
        period_seconds = 30
      }
    }
  }

  # The deploy pipeline owns the running image; Terraform owns everything else.
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]

    # The API refuses to start with a paid provider and no ceiling; fail the plan
    # instead of a deploy.
    precondition {
      condition     = var.oidc_issuer == "" || var.oidc_audience != ""
      error_message = "oidc_audience is required when oidc_issuer is set."
    }
    precondition {
      condition     = var.environment != "production" || var.oidc_issuer != ""
      error_message = "Production requires oidc_issuer and oidc_audience: it has no other way to authenticate."
    }
    precondition {
      condition = var.ai_provider == "stub" || (
        var.ai_price_input_usd_per_mtok != "" && var.ai_price_output_usd_per_mtok != "" &&
        var.ai_budget_global_monthly_usd != "" && var.ai_budget_org_daily_usd != ""
      )
      error_message = "A paid ai_provider needs ai_price_input_usd_per_mtok, ai_price_output_usd_per_mtok, ai_budget_global_monthly_usd and ai_budget_org_daily_usd."
    }
  }

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_iam_member.api_database_url,
    google_project_iam_member.api_cloudsql,
  ]
}

# ---------------------------------------------------------------------------
# Web service
# ---------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "web" {
  count               = local.create_services ? 1 : 0
  name                = "${local.prefix}-web"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = local.is_prod

  template {
    service_account = google_service_account.web.email

    scaling {
      min_instance_count = var.web_min_instances
      max_instance_count = var.web_max_instances
    }

    containers {
      image = var.web_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      startup_probe {
        http_get {
          path = "/"
        }
        period_seconds    = 3
        failure_threshold = 20
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

# Both services are public by design: users reach the web app directly, and the
# API is protected by bearer tokens (the web tier proxies to it over the internet).
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  count    = local.create_services ? 1 : 0
  location = var.region
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "web_public" {
  count    = local.create_services ? 1 : 0
  location = var.region
  name     = google_cloud_run_v2_service.web[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_domain_mapping" "web" {
  count    = local.create_services && var.web_domain != "" ? 1 : 0
  location = var.region
  name     = var.web_domain

  metadata {
    namespace = var.project_id
  }
  spec {
    route_name = google_cloud_run_v2_service.web[0].name
  }
}

# ---------------------------------------------------------------------------
# CI/CD identity: GitHub Actions deploys with short-lived federated credentials,
# so no service-account key ever exists.
# ---------------------------------------------------------------------------
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "${local.prefix}-github"
  display_name              = "GitHub Actions (${var.environment})"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  # Only workflows from this repository can obtain credentials.
  attribute_condition = "assertion.repository == \"${var.github_repository}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  account_id   = "${local.prefix}-deployer"
  display_name = "HelixOS deploy pipeline (${var.environment})"
}

resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

resource "google_project_iam_member" "deployer_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_artifact_registry_repository_iam_member" "deployer_push" {
  repository = google_artifact_registry_repository.images.name
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

# Deploying a revision "as" a runtime service account requires acting as it.
resource "google_service_account_iam_member" "deployer_acts_as_api" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_acts_as_web" {
  service_account_id = google_service_account.web.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}
