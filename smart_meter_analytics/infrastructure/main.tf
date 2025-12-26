provider "google" {
  project = var.project_id
  region  = var.region
}

# -----------------------------------------------------------------------------
# Cloud Storage Buckets
# -----------------------------------------------------------------------------

# Bucket for Dataflow temp/staging files
resource "google_storage_bucket" "dataflow_artifacts" {
  name          = "${var.project_id}-ami-dataflow-artifacts"
  location      = var.region
  storage_class = "STANDARD"
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }
  
  labels = var.labels
}

# Bucket for raw data archive (JSON/CSV data lake)
resource "google_storage_bucket" "raw_archive" {
  name          = "${var.project_id}-ami-raw-archive"
  location      = var.region
  storage_class = "STANDARD"
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = var.raw_archive_retention_days
    }
    action {
      type = "Delete"
    }
  }
  
  labels = var.labels
}

# -----------------------------------------------------------------------------
# Pub/Sub Topic and Subscriptions
# -----------------------------------------------------------------------------

resource "google_pubsub_topic" "ami_meter_data" {
  name = var.pubsub_topic_name
  
  message_retention_duration = "${var.pubsub_message_retention_hours * 3600}s"
  
  labels = var.labels
}

resource "google_pubsub_subscription" "ami_meter_data_sub" {
  name  = var.pubsub_subscription_name
  topic = google_pubsub_topic.ami_meter_data.id
  
  # Pull subscription for Dataflow
  ack_deadline_seconds       = 60
  message_retention_duration = "${var.pubsub_message_retention_hours * 3600}s"
  retain_acked_messages      = false
  
  # Enable exactly-once delivery for streaming pipelines
  enable_exactly_once_delivery = true
  
  # Expiration policy (never expire for active subscription)
  expiration_policy {
    ttl = ""
  }
  
  # Optional dead letter policy
  dynamic "dead_letter_policy" {
    for_each = var.enable_dead_letter ? [1] : []
    content {
      dead_letter_topic     = google_pubsub_topic.ami_meter_dlq[0].id
      max_delivery_attempts = var.max_delivery_attempts
    }
  }
  
  labels = var.labels
}

# Dead Letter Queue Topic (optional)
resource "google_pubsub_topic" "ami_meter_dlq" {
  count = var.enable_dead_letter ? 1 : 0
  
  name = "${var.pubsub_topic_name}-dlq"
  
  message_retention_duration = "${var.pubsub_message_retention_hours * 3600}s"
  
  labels = var.labels
}

# Dead Letter Queue Subscription
resource "google_pubsub_subscription" "ami_meter_dlq_sub" {
  count = var.enable_dead_letter ? 1 : 0
  
  name  = "${var.pubsub_topic_name}-dlq-sub"
  topic = google_pubsub_topic.ami_meter_dlq[0].id
  
  ack_deadline_seconds       = 60
  message_retention_duration = "${var.pubsub_message_retention_hours * 3600}s"
  
  labels = var.labels
}

# -----------------------------------------------------------------------------
# BigQuery Dataset and Tables
# -----------------------------------------------------------------------------

resource "google_bigquery_dataset" "smart_grid_analytics" {
  dataset_id    = var.bq_dataset_id
  friendly_name = "Smart Grid Analytics"
  description   = "AMI 2.0 smart meter analytics dataset for high-frequency grid monitoring"
  location      = var.bq_location
  
  # Only set table expiration if > 0 (0 means no expiration)
  default_table_expiration_ms     = var.bq_table_expiration_days > 0 ? var.bq_table_expiration_days * 24 * 3600 * 1000 : null
  default_partition_expiration_ms = var.bq_partition_expiration_days > 0 ? var.bq_partition_expiration_days * 24 * 3600 * 1000 : null
  
  labels = var.labels
}

resource "google_bigquery_table" "raw_meter_readings" {
  dataset_id = google_bigquery_dataset.smart_grid_analytics.dataset_id
  table_id   = "raw_meter_readings"
  
  description = "Raw seconds-level AMI 2.0 meter readings"
  
  # Time partitioning by event timestamp
  time_partitioning {
    type  = "DAY"
    field = "event_ts"
  }
  
  # Clustering for efficient queries
  clustering = ["pole_id", "meter_id"]
  
  schema = jsonencode([
    {
      name        = "event_ts"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "Event timestamp (UTC)"
    },
    {
      name        = "ingest_ts"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "Dataflow ingestion timestamp"
    },
    {
      name        = "meter_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Unique meter identifier"
    },
    {
      name        = "pole_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Pole/gateway identifier"
    },
    {
      name        = "seq"
      type        = "INT64"
      mode        = "NULLABLE"
      description = "Monotonically increasing sequence number"
    },
    {
      name        = "voltage_v"
      type        = "FLOAT64"
      mode        = "REQUIRED"
      description = "RMS voltage in volts"
    },
    {
      name        = "current_a"
      type        = "FLOAT64"
      mode        = "REQUIRED"
      description = "RMS current in amperes"
    },
    {
      name        = "power_kw"
      type        = "FLOAT64"
      mode        = "REQUIRED"
      description = "Active power in kilowatts"
    },
    {
      name        = "reactive_kvar"
      type        = "FLOAT64"
      mode        = "NULLABLE"
      description = "Reactive power in kVAR"
    },
    {
      name        = "freq_hz"
      type        = "FLOAT64"
      mode        = "NULLABLE"
      description = "System frequency in Hz"
    },
    {
      name        = "quality_flags"
      type        = "STRING"
      mode        = "REPEATED"
      description = "Data quality flags"
    },
    {
      name        = "network_profile"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Network backhaul type (wired/5g/satellite)"
    }
  ])
  
  labels = var.labels
}

# View for 5-minute aggregates
resource "google_bigquery_table" "v_5min_pole" {
  dataset_id = google_bigquery_dataset.smart_grid_analytics.dataset_id
  table_id   = "v_5min_pole"
  
  description = "5-minute aggregated readings per pole"
  
  view {
    query = <<-SQL
      SELECT
        pole_id,
        TIMESTAMP_TRUNC(event_ts, MINUTE) AS interval_start,
        FLOOR(EXTRACT(MINUTE FROM event_ts) / 5) * 5 AS minute_bucket,
        COUNT(*) AS reading_count,
        COUNT(DISTINCT meter_id) AS meter_count,
        AVG(voltage_v) AS avg_voltage_v,
        MIN(voltage_v) AS min_voltage_v,
        MAX(voltage_v) AS max_voltage_v,
        STDDEV(voltage_v) AS stddev_voltage_v,
        AVG(current_a) AS avg_current_a,
        SUM(power_kw) AS total_power_kw,
        AVG(power_kw) AS avg_power_kw,
        MAX(power_kw) AS peak_power_kw,
        AVG(freq_hz) AS avg_freq_hz
      FROM `${var.project_id}.${var.bq_dataset_id}.raw_meter_readings`
      GROUP BY pole_id, interval_start, minute_bucket
    SQL
    use_legacy_sql = false
  }
  
  labels = var.labels
  
  depends_on = [google_bigquery_table.raw_meter_readings]
}

# -----------------------------------------------------------------------------
# Service Accounts and IAM
# -----------------------------------------------------------------------------

# Service account for edge devices (publishers)
resource "google_service_account" "edge_device_sa" {
  account_id   = "edge-device-sa"
  display_name = "Edge Device Service Account"
  description  = "Service account for edge devices publishing to Pub/Sub"
}

# Service account for Dataflow workers
resource "google_service_account" "dataflow_sa" {
  account_id   = "dataflow-sa"
  display_name = "Dataflow Service Account"
  description  = "Service account for Dataflow streaming pipeline"
}

# Service account for Cloud Run API
resource "google_service_account" "api_sa" {
  account_id   = "api-sa"
  display_name = "API Service Account"
  description  = "Service account for Cloud Run API service"
}

# Edge device permissions - Pub/Sub publisher
resource "google_pubsub_topic_iam_member" "edge_publisher" {
  topic  = google_pubsub_topic.ami_meter_data.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.edge_device_sa.email}"
}

# Dataflow permissions
resource "google_project_iam_member" "dataflow_worker" {
  project = var.project_id
  role    = "roles/dataflow.worker"
  member  = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

resource "google_pubsub_subscription_iam_member" "dataflow_subscriber" {
  subscription = google_pubsub_subscription.ami_meter_data_sub.id
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

resource "google_bigquery_dataset_iam_member" "dataflow_bq_editor" {
  dataset_id = google_bigquery_dataset.smart_grid_analytics.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

resource "google_storage_bucket_iam_member" "dataflow_gcs_artifacts" {
  bucket = google_storage_bucket.dataflow_artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

resource "google_storage_bucket_iam_member" "dataflow_gcs_archive" {
  bucket = google_storage_bucket.raw_archive.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

# API service permissions
resource "google_project_iam_member" "api_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.api_sa.email}"
}

resource "google_bigquery_dataset_iam_member" "api_bq_viewer" {
  dataset_id = google_bigquery_dataset.smart_grid_analytics.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.api_sa.email}"
}

# DLQ permissions for Pub/Sub service account (if enabled)
resource "google_pubsub_topic_iam_member" "pubsub_dlq_publisher" {
  count = var.enable_dead_letter ? 1 : 0
  
  topic  = google_pubsub_topic.ami_meter_dlq[0].id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${var.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "pubsub_dlq_subscriber" {
  count = var.enable_dead_letter ? 1 : 0
  
  subscription = google_pubsub_subscription.ami_meter_data_sub.id
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${var.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

# -----------------------------------------------------------------------------
# Service Account Keys (for local development/testing)
# -----------------------------------------------------------------------------

resource "google_service_account_key" "edge_device_key" {
  count = var.create_sa_keys ? 1 : 0
  
  service_account_id = google_service_account.edge_device_sa.name
  public_key_type    = "TYPE_X509_PEM_FILE"
}

resource "local_file" "edge_device_key_file" {
  count = var.create_sa_keys ? 1 : 0
  
  content         = base64decode(google_service_account_key.edge_device_key[0].private_key)
  filename        = "${path.module}/keys/edge-device-sa-key.json"
  file_permission = "0600"
}

# -----------------------------------------------------------------------------
# Cloud Monitoring Dashboard
# -----------------------------------------------------------------------------

resource "google_monitoring_dashboard" "ami_realtime_dashboard" {
  dashboard_json = jsonencode({
    displayName = "AMI 2.0 Smart Meter Real-Time Dashboard"
    labels = {
      environment = "demo"
    }
    mosaicLayout = {
      columns = 12
      tiles = [
        # Row 1: Key Metrics Overview
        {
          width  = 4
          height = 4
          widget = {
            title = "Total Messages Ingested"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type=\"pubsub_subscription\" AND resource.labels.subscription_id=\"${var.pubsub_subscription_name}\" AND metric.type=\"pubsub.googleapis.com/subscription/num_delivered_messages\""
                  aggregation = {
                    alignmentPeriod    = "60s"
                    perSeriesAligner   = "ALIGN_RATE"
                    crossSeriesReducer = "REDUCE_SUM"
                  }
                }
              }
              sparkChartView = {
                sparkChartType = "SPARK_LINE"
              }
            }
          }
        },
        {
          xPos   = 4
          width  = 4
          height = 4
          widget = {
            title = "Pub/Sub Backlog"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type=\"pubsub_subscription\" AND resource.labels.subscription_id=\"${var.pubsub_subscription_name}\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\""
                  aggregation = {
                    alignmentPeriod  = "60s"
                    perSeriesAligner = "ALIGN_MEAN"
                  }
                }
              }
              thresholds = [
                {
                  color     = "YELLOW"
                  direction = "ABOVE"
                  value     = 100
                },
                {
                  color     = "RED"
                  direction = "ABOVE"
                  value     = 1000
                }
              ]
            }
          }
        },
        {
          xPos   = 8
          width  = 4
          height = 4
          widget = {
            title = "Dataflow Processing Lag"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type=\"dataflow_job\" AND metric.type=\"dataflow.googleapis.com/job/system_lag\""
                  aggregation = {
                    alignmentPeriod  = "60s"
                    perSeriesAligner = "ALIGN_MAX"
                  }
                }
              }
              thresholds = [
                {
                  color     = "YELLOW"
                  direction = "ABOVE"
                  value     = 30
                },
                {
                  color     = "RED"
                  direction = "ABOVE"
                  value     = 120
                }
              ]
            }
          }
        },
        # Row 2: Custom AMI Metrics
        {
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "Average Voltage by Pole"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"custom.googleapis.com/ami/voltage_avg\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_MEAN"
                      }
                    }
                  }
                  plotType = "LINE"
                }
              ]
              yAxis = {
                label = "Voltage (V)"
                scale = "LINEAR"
              }
              thresholds = [
                {
                  label     = "Sag Threshold"
                  value     = 220
                },
                {
                  label     = "Nominal"
                  value     = 240
                }
              ]
            }
          }
        },
        {
          yPos   = 4
          xPos   = 6
          width  = 6
          height = 4
          widget = {
            title = "Total Power Consumption (kW)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"custom.googleapis.com/ami/power_total_kw\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_MEAN"
                      }
                    }
                  }
                  plotType = "STACKED_AREA"
                }
              ]
              yAxis = {
                label = "Power (kW)"
                scale = "LINEAR"
              }
            }
          }
        },
        # Row 3: Anomaly and Health Metrics
        {
          yPos   = 8
          width  = 4
          height = 4
          widget = {
            title = "Voltage Sag Events (5 min)"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/ami/voltage_sag_count\""
                  aggregation = {
                    alignmentPeriod    = "300s"
                    perSeriesAligner   = "ALIGN_SUM"
                    crossSeriesReducer = "REDUCE_SUM"
                  }
                }
              }
              thresholds = [
                {
                  color     = "YELLOW"
                  direction = "ABOVE"
                  value     = 5
                },
                {
                  color     = "RED"
                  direction = "ABOVE"
                  value     = 20
                }
              ]
            }
          }
        },
        {
          yPos   = 8
          xPos   = 4
          width  = 4
          height = 4
          widget = {
            title = "Meter Health Score"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/ami/health_score\""
                  aggregation = {
                    alignmentPeriod    = "60s"
                    perSeriesAligner   = "ALIGN_MEAN"
                    crossSeriesReducer = "REDUCE_MEAN"
                  }
                }
              }
              thresholds = [
                {
                  color     = "RED"
                  direction = "BELOW"
                  value     = 80
                },
                {
                  color     = "YELLOW"
                  direction = "BELOW"
                  value     = 95
                }
              ]
            }
          }
        },
        {
          yPos   = 8
          xPos   = 8
          width  = 4
          height = 4
          widget = {
            title = "Active Meters"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "metric.type=\"custom.googleapis.com/ami/active_meter_count\""
                  aggregation = {
                    alignmentPeriod    = "60s"
                    perSeriesAligner   = "ALIGN_MEAN"
                    crossSeriesReducer = "REDUCE_SUM"
                  }
                }
              }
            }
          }
        },
        # Row 4: Detailed Charts
        {
          yPos   = 12
          width  = 6
          height = 5
          widget = {
            title = "Voltage Distribution (Min/Avg/Max)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"custom.googleapis.com/ami/voltage_min\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_MIN"
                      }
                    }
                  }
                  legendTemplate = "Min Voltage"
                  plotType       = "LINE"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"custom.googleapis.com/ami/voltage_avg\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_MEAN"
                      }
                    }
                  }
                  legendTemplate = "Avg Voltage"
                  plotType       = "LINE"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "metric.type=\"custom.googleapis.com/ami/voltage_max\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_MAX"
                      }
                    }
                  }
                  legendTemplate = "Max Voltage"
                  plotType       = "LINE"
                }
              ]
              yAxis = {
                label = "Voltage (V)"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          yPos   = 12
          xPos   = 6
          width  = 6
          height = 5
          widget = {
            title = "BigQuery Streaming Inserts"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"bigquery_dataset\" AND metric.type=\"bigquery.googleapis.com/storage/streaming_insert_count\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_RATE"
                        crossSeriesReducer = "REDUCE_SUM"
                      }
                    }
                  }
                  plotType = "LINE"
                }
              ]
              yAxis = {
                label = "Inserts/sec"
                scale = "LINEAR"
              }
            }
          }
        }
      ]
    }
  })

  project = var.project_id
}

# Custom Metric Descriptors for AMI data
resource "google_monitoring_metric_descriptor" "voltage_avg" {
  project      = var.project_id
  type         = "custom.googleapis.com/ami/voltage_avg"
  metric_kind  = "GAUGE"
  value_type   = "DOUBLE"
  display_name = "Average Voltage"
  description  = "Average RMS voltage across meters at a pole"
  unit         = "V"
  
  labels {
    key         = "pole_id"
    value_type  = "STRING"
    description = "Pole/gateway identifier"
  }
}

resource "google_monitoring_metric_descriptor" "voltage_min" {
  project      = var.project_id
  type         = "custom.googleapis.com/ami/voltage_min"
  metric_kind  = "GAUGE"
  value_type   = "DOUBLE"
  display_name = "Minimum Voltage"
  description  = "Minimum RMS voltage at a pole"
  unit         = "V"
  
  labels {
    key         = "pole_id"
    value_type  = "STRING"
    description = "Pole/gateway identifier"
  }
}

resource "google_monitoring_metric_descriptor" "voltage_max" {
  project      = var.project_id
  type         = "custom.googleapis.com/ami/voltage_max"
  metric_kind  = "GAUGE"
  value_type   = "DOUBLE"
  display_name = "Maximum Voltage"
  description  = "Maximum RMS voltage at a pole"
  unit         = "V"
  
  labels {
    key         = "pole_id"
    value_type  = "STRING"
    description = "Pole/gateway identifier"
  }
}

resource "google_monitoring_metric_descriptor" "power_total" {
  project      = var.project_id
  type         = "custom.googleapis.com/ami/power_total_kw"
  metric_kind  = "GAUGE"
  value_type   = "DOUBLE"
  display_name = "Total Power"
  description  = "Total active power consumption at a pole"
  unit         = "kW"
  
  labels {
    key         = "pole_id"
    value_type  = "STRING"
    description = "Pole/gateway identifier"
  }
}

resource "google_monitoring_metric_descriptor" "voltage_sag_count" {
  project      = var.project_id
  type         = "custom.googleapis.com/ami/voltage_sag_count"
  metric_kind  = "GAUGE"
  value_type   = "INT64"
  display_name = "Voltage Sag Count"
  description  = "Number of voltage sag events detected"
  unit         = "1"
  
  labels {
    key         = "pole_id"
    value_type  = "STRING"
    description = "Pole/gateway identifier"
  }
}

resource "google_monitoring_metric_descriptor" "health_score" {
  project      = var.project_id
  type         = "custom.googleapis.com/ami/health_score"
  metric_kind  = "GAUGE"
  value_type   = "DOUBLE"
  display_name = "Health Score"
  description  = "Overall health score (0-100) based on voltage quality"
  unit         = "%"
  
  labels {
    key         = "pole_id"
    value_type  = "STRING"
    description = "Pole/gateway identifier"
  }
}

resource "google_monitoring_metric_descriptor" "active_meter_count" {
  project      = var.project_id
  type         = "custom.googleapis.com/ami/active_meter_count"
  metric_kind  = "GAUGE"
  value_type   = "INT64"
  display_name = "Active Meter Count"
  description  = "Number of active meters at a pole"
  unit         = "1"
  
  labels {
    key         = "pole_id"
    value_type  = "STRING"
    description = "Pole/gateway identifier"
  }
}
