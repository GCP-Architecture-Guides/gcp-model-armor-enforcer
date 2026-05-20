terraform {
  required_version = ">= 1.3.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.43.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 6.43.0"
    }
  }

  # Configured dynamically in Cloud Build via -backend-config during init
  backend "gcs" {}
}

provider "google" {}
provider "google-beta" {}

# Provisions a Folder or Org-level Floor Setting (baseline compliance enforcement)
resource "google_model_armor_floorsetting" "folder_or_org_floor" {
  provider = google-beta
  parent   = var.parent_id # e.g., "folders/123456" or "organizations/789012"
  location = "global"

  enable_floor_setting_enforcement = true

  filter_config {
    # Hardcode Malicious URI detection to ENABLED
    malicious_uri_filter_settings {
      filter_enforcement = "ENABLED"
    }

    # Hardcode Prompt Injection safety baseline to HIGH
    pi_and_jailbreak_filter_settings {
      filter_enforcement = "ENABLED"
      confidence_level   = "HIGH"
    }

    # Hardcode Responsible AI (RAI) safety filters to HIGH
    rai_settings {
      rai_filters {
        filter_type      = "HATE_SPEECH"
        confidence_level = "HIGH"
      }
      rai_filters {
        filter_type      = "HARASSMENT"
        confidence_level = "HIGH"
      }
      rai_filters {
        filter_type      = "SEXUALLY_EXPLICIT"
        confidence_level = "HIGH"
      }
      rai_filters {
        filter_type      = "DANGEROUS"
        confidence_level = "HIGH"
      }
    }

    # Baseline Sensitive Data Protection (PII) Filter
    sdp_settings {
      basic_config {
        filter_enforcement = var.pii_inspection_enabled ? "ENABLED" : "DISABLED"
      }
    }
  }
}

# Invoke the Model Armor Child Module for each targeted project
module "model_armor_deployment" {
  source   = "./modules/model_armor"
  for_each = toset(var.target_projects)

  providers = {
    google      = google
    google-beta = google-beta
  }

  project_id              = each.value
  location                = var.location
  pii_inspection_enabled  = var.pii_inspection_enabled
  log_template_operations = var.log_template_operations
  log_sanitize_operations = var.log_sanitize_operations
}
