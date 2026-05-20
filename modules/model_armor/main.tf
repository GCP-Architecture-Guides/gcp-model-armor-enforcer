terraform {
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
}

# Enable the Model Armor API in target project
resource "google_project_service" "model_armor_api" {
  project            = var.project_id
  service            = "modelarmor.googleapis.com"
  disable_on_destroy = false
}

# Enable the Vertex AI API in target project (mandatory for Model Armor integrations)
resource "google_project_service" "vertex_ai_api" {
  project            = var.project_id
  service            = "aiplatform.googleapis.com"
  disable_on_destroy = false
}

# Create the Model Armor Template
resource "google_model_armor_template" "enforcer_template" {
  provider    = google-beta
  project     = var.project_id
  location    = var.location
  template_id = "model-armor-enforcer-template"

  # Expose operations and sanitization logging variables
  template_metadata {
    log_template_operations = var.log_template_operations
    log_sanitize_operations = var.log_sanitize_operations
  }

  filter_config {
    # Hardcode Malicious URI Filter to ENABLED
    malicious_uri_filter_settings {
      filter_enforcement = "ENABLED"
    }

    # Hardcode Prompt Injection and Jailbreak Filter to HIGH
    pi_and_jailbreak_filter_settings {
      filter_enforcement = "ENABLED"
      confidence_level   = "HIGH"
    }

    # Hardcode Responsible AI (RAI) Filters to HIGH
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

    # Sensitive Data Protection (SDP/PII) Filter
    sdp_settings {
      basic_config {
        filter_enforcement = var.pii_inspection_enabled ? "ENABLED" : "DISABLED"
      }
    }
  }

  depends_on = [
    google_project_service.model_armor_api,
    google_project_service.vertex_ai_api
  ]
}
