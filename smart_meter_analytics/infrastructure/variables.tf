# -----------------------------------------------------------------------------
# Required Variables
# -----------------------------------------------------------------------------

variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "region" {
  description = "The GCP region for resources"
  type        = string
  default     = "us-central1"
}

# -----------------------------------------------------------------------------
# Pub/Sub Configuration
# -----------------------------------------------------------------------------

variable "pubsub_topic_name" {
  description = "Name of the Pub/Sub topic for meter data"
  type        = string
  default     = "ami-meter-data"
}

variable "pubsub_subscription_name" {
  description = "Name of the Pub/Sub subscription for Dataflow"
  type        = string
  default     = "ami-meter-data-sub"
}

variable "pubsub_message_retention_hours" {
  description = "Message retention duration in hours"
  type        = number
  default     = 24
}

variable "enable_dead_letter" {
  description = "Enable dead letter queue for failed messages"
  type        = bool
  default     = true
}

variable "max_delivery_attempts" {
  description = "Maximum delivery attempts before sending to DLQ"
  type        = number
  default     = 5
}

# -----------------------------------------------------------------------------
# BigQuery Configuration
# -----------------------------------------------------------------------------

variable "bq_dataset_id" {
  description = "BigQuery dataset ID"
  type        = string
  default     = "smart_grid_analytics"
}

variable "bq_location" {
  description = "BigQuery dataset location"
  type        = string
  default     = "US"
}

variable "bq_table_expiration_days" {
  description = "Default table expiration in days (0 for no expiration)"
  type        = number
  default     = 0
}

variable "bq_partition_expiration_days" {
  description = "Default partition expiration in days"
  type        = number
  default     = 90
}

# -----------------------------------------------------------------------------
# Storage Configuration
# -----------------------------------------------------------------------------

variable "raw_archive_retention_days" {
  description = "Retention period for raw archive data in days"
  type        = number
  default     = 30
}

# -----------------------------------------------------------------------------
# Service Account Configuration
# -----------------------------------------------------------------------------

variable "create_sa_keys" {
  description = "Create service account keys for local development"
  type        = bool
  default     = false
}

variable "project_number" {
  description = "The GCP project number (for service account references)"
  type        = string
}

# -----------------------------------------------------------------------------
# Labels
# -----------------------------------------------------------------------------

variable "labels" {
  description = "Labels to apply to all resources"
  type        = map(string)
  default = {
    project     = "ami-smart-meter"
    environment = "tutorial"
    managed_by  = "terraform"
  }
}
