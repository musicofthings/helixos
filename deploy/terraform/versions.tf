terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state holds the generated database password: use a private, versioned
  # bucket with restricted access. Supply it at init time:
  #   terraform init -backend-config="bucket=<state-bucket>" -backend-config="prefix=helixos/<env>"
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}
