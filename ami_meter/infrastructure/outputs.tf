# -----------------------------------------------------------------------------
# Pub/Sub Outputs
# -----------------------------------------------------------------------------

output "pubsub_topic_name" {
  description = "Name of the Pub/Sub topic"
  value       = google_pubsub_topic.ami_meter_data.name
}

output "pubsub_topic_id" {
  description = "Full ID of the Pub/Sub topic"
  value       = google_pubsub_topic.ami_meter_data.id
}

output "pubsub_subscription_name" {
  description = "Name of the Pub/Sub subscription"
  value       = google_pubsub_subscription.ami_meter_data_sub.name
}

output "pubsub_subscription_id" {
  description = "Full ID of the Pub/Sub subscription"
  value       = google_pubsub_subscription.ami_meter_data_sub.id
}

output "pubsub_dlq_topic_name" {
  description = "Name of the Dead Letter Queue topic"
  value       = var.enable_dead_letter ? google_pubsub_topic.ami_meter_dlq[0].name : null
}

# -----------------------------------------------------------------------------
# Storage Outputs
# -----------------------------------------------------------------------------

output "dataflow_artifacts_bucket" {
  description = "Name of the Dataflow artifacts bucket"
  value       = google_storage_bucket.dataflow_artifacts.name
}

output "dataflow_artifacts_bucket_url" {
  description = "URL of the Dataflow artifacts bucket"
  value       = google_storage_bucket.dataflow_artifacts.url
}

output "raw_archive_bucket" {
  description = "Name of the raw archive bucket"
  value       = google_storage_bucket.raw_archive.name
}

output "raw_archive_bucket_url" {
  description = "URL of the raw archive bucket"
  value       = google_storage_bucket.raw_archive.url
}

# -----------------------------------------------------------------------------
# BigQuery Outputs
# -----------------------------------------------------------------------------

output "bq_dataset_id" {
  description = "BigQuery dataset ID"
  value       = google_bigquery_dataset.smart_grid_analytics.dataset_id
}

output "bq_dataset_full_id" {
  description = "Full BigQuery dataset ID"
  value       = "${var.project_id}:${google_bigquery_dataset.smart_grid_analytics.dataset_id}"
}

output "bq_raw_table_id" {
  description = "BigQuery raw meter readings table ID"
  value       = google_bigquery_table.raw_meter_readings.table_id
}

output "bq_raw_table_full_id" {
  description = "Full BigQuery raw meter readings table ID"
  value       = "${var.project_id}:${google_bigquery_dataset.smart_grid_analytics.dataset_id}.${google_bigquery_table.raw_meter_readings.table_id}"
}

# -----------------------------------------------------------------------------
# Service Account Outputs
# -----------------------------------------------------------------------------

output "edge_device_sa_email" {
  description = "Edge device service account email"
  value       = google_service_account.edge_device_sa.email
}

output "dataflow_sa_email" {
  description = "Dataflow service account email"
  value       = google_service_account.dataflow_sa.email
}

output "api_sa_email" {
  description = "API service account email"
  value       = google_service_account.api_sa.email
}

# -----------------------------------------------------------------------------
# Convenience Outputs for Scripts
# -----------------------------------------------------------------------------

output "dataflow_launch_command" {
  description = "Example command to launch the Dataflow pipeline"
  value       = <<-EOT
    python -m cloud_processing.streaming_pipeline \
      --runner DataflowRunner \
      --project=${var.project_id} \
      --region=${var.region} \
      --input_subscription=projects/${var.project_id}/subscriptions/${google_pubsub_subscription.ami_meter_data_sub.name} \
      --output_bq_table=${var.project_id}:${google_bigquery_dataset.smart_grid_analytics.dataset_id}.${google_bigquery_table.raw_meter_readings.table_id} \
      --raw_archive_bucket=${google_storage_bucket.raw_archive.name} \
      --temp_location=gs://${google_storage_bucket.dataflow_artifacts.name}/temp \
      --staging_location=gs://${google_storage_bucket.dataflow_artifacts.name}/staging \
      --service_account_email=${google_service_account.dataflow_sa.email} \
      --worker_machine_type=e2-standard-2 \
      --max_num_workers=2 \
      --streaming
  EOT
}

output "edge_simulator_env" {
  description = "Environment variables for edge simulator"
  value       = <<-EOT
    export GOOGLE_CLOUD_PROJECT=${var.project_id}
    export PUBSUB_TOPIC=${google_pubsub_topic.ami_meter_data.name}
    export GOOGLE_APPLICATION_CREDENTIALS=path/to/edge-device-sa-key.json
  EOT
}
