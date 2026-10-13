variable "project_id" {
  type        = string
  description = "GCP project for this environment. Use a separate project per environment."
}

variable "region" {
  type        = string
  default     = "asia-south1"
  description = "Region for Cloud Run, Cloud SQL and Artifact Registry."
}

variable "environment" {
  type        = string
  description = "staging or production; becomes HELIX_ENV."

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "name" {
  type        = string
  default     = "helixos"
  description = "Prefix for resource names."
}

variable "github_repository" {
  type        = string
  description = "owner/repo whose workflows may deploy (Workload Identity Federation)."
}

# ---- Application images (the deploy pipeline owns these after the first apply) ----
variable "api_image" {
  type        = string
  default     = ""
  description = "API image. Leave empty on the first apply: services are only created once both images exist."
}

variable "web_image" {
  type        = string
  default     = ""
  description = "Web image. Leave empty on the first apply."
}

# ---- Public addresses ----
variable "web_url" {
  type        = string
  default     = ""
  description = "Public https URL of the web app (the CORS origin). Defaults to the service's deterministic run.app URL."
}

variable "api_url" {
  type        = string
  default     = ""
  description = "Public https URL of the API, baked into the web image as its proxy target. Defaults to the deterministic run.app URL."
}

variable "web_domain" {
  type        = string
  default     = ""
  description = "Optional custom domain for the web app (must be verified in Search Console). Managed TLS is provisioned by Cloud Run."
}

# ---- Authentication ----
variable "oidc_issuer" {
  type        = string
  description = "OpenID Connect issuer URL; must equal the tokens' iss claim."
}

variable "oidc_audience" {
  type        = string
  description = "Audience the API requires in tokens."
}

variable "enable_demo_tokens" {
  type        = bool
  default     = false
  description = "Staging only: also accept the documented demo tokens. Never applied in production."
}

# ---- AI ----
variable "ai_provider" {
  type        = string
  default     = "openai"
  description = "openai | vertex | stub (stub is rejected in production)."

  validation {
    condition     = contains(["openai", "vertex", "stub"], var.ai_provider)
    error_message = "ai_provider must be openai, vertex or stub."
  }
}

# ---- Sizing ----
variable "db_tier" {
  type        = string
  default     = "db-custom-1-3840"
  description = "Cloud SQL machine tier."
}

variable "db_high_availability" {
  type        = bool
  default     = false
  description = "Regional (HA) Cloud SQL. Recommended for production."
}

variable "api_min_instances" {
  type        = number
  default     = 1
  description = "Keep one warm: AI sessions live in process memory. The API is capped at one instance (see main.tf)."
}

variable "web_min_instances" {
  type    = number
  default = 0
}

variable "web_max_instances" {
  type    = number
  default = 4
}
