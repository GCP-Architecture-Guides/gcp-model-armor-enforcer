variable "project_id" {
  type        = string
  description = "The GCP Project ID where Model Armor resources will be provisioned."
}

variable "location" {
  type        = string
  description = "The regional location for Model Armor templates (e.g. us-central1)."
  default     = "us-central1"
}

variable "pii_inspection_enabled" {
  type        = bool
  description = "Flag to enable or disable PII inspection via Sensitive Data Protection (SDP)."
  default     = true
}

variable "log_template_operations" {
  type        = bool
  description = "Whether to log CRUD template operations."
  default     = true
}

variable "log_sanitize_operations" {
  type        = bool
  description = "Whether to log detailed input/output payloads of sanitization requests."
  default     = false
}
