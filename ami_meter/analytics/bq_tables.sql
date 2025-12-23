-- ============================================================================
-- BigQuery Table DDL Statements
-- ============================================================================
-- Use these statements to create tables manually if not using Terraform.
-- Replace PROJECT_ID with your actual project ID.
-- ============================================================================

-- Create dataset
CREATE SCHEMA IF NOT EXISTS `PROJECT_ID.smart_grid_analytics`
OPTIONS (
  description = 'AMI 2.0 smart meter analytics dataset',
  location = 'US'
);

-- ============================================================================
-- Raw Meter Readings Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS `PROJECT_ID.smart_grid_analytics.raw_meter_readings` (
  event_ts TIMESTAMP NOT NULL OPTIONS(description='Event timestamp (UTC)'),
  ingest_ts TIMESTAMP OPTIONS(description='Dataflow ingestion timestamp'),
  meter_id STRING NOT NULL OPTIONS(description='Unique meter identifier'),
  pole_id STRING NOT NULL OPTIONS(description='Pole/gateway identifier'),
  seq INT64 OPTIONS(description='Monotonically increasing sequence number'),
  voltage_v FLOAT64 NOT NULL OPTIONS(description='RMS voltage in volts'),
  current_a FLOAT64 NOT NULL OPTIONS(description='RMS current in amperes'),
  power_kw FLOAT64 NOT NULL OPTIONS(description='Active power in kilowatts'),
  reactive_kvar FLOAT64 OPTIONS(description='Reactive power in kVAR'),
  freq_hz FLOAT64 OPTIONS(description='System frequency in Hz'),
  quality_flags ARRAY<STRING> OPTIONS(description='Data quality flags'),
  network_profile STRING OPTIONS(description='Network backhaul type')
)
PARTITION BY DATE(event_ts)
CLUSTER BY pole_id, meter_id
OPTIONS (
  description = 'Raw seconds-level AMI 2.0 meter readings',
  partition_expiration_days = 90,
  labels = [('project', 'ami-smart-meter'), ('environment', 'tutorial')]
);

-- ============================================================================
-- Minute Aggregation Table (Optional)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `PROJECT_ID.smart_grid_analytics.minute_agg_pole` (
  pole_id STRING NOT NULL,
  window_start TIMESTAMP NOT NULL,
  reading_count INT64 NOT NULL,
  meter_count INT64 NOT NULL,
  avg_voltage_v FLOAT64 NOT NULL,
  min_voltage_v FLOAT64 NOT NULL,
  max_voltage_v FLOAT64 NOT NULL,
  total_power_kw FLOAT64 NOT NULL,
  avg_power_kw FLOAT64 NOT NULL
)
PARTITION BY DATE(window_start)
CLUSTER BY pole_id
OPTIONS (
  description = 'Per-minute aggregated readings by pole',
  partition_expiration_days = 30
);

-- ============================================================================
-- DR Baseline Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS `PROJECT_ID.smart_grid_analytics.dr_5min_baseline` (
  pole_id STRING NOT NULL,
  hour_of_day INT64 NOT NULL,
  minute_bucket INT64 NOT NULL,
  time_of_day STRING NOT NULL,
  baseline_avg_kw FLOAT64,
  baseline_median_kw FLOAT64,
  baseline_p10_kw FLOAT64,
  baseline_p90_kw FLOAT64,
  baseline_stddev_kw FLOAT64,
  avg_meter_count INT64,
  baseline_days_count INT64,
  computed_at TIMESTAMP
)
CLUSTER BY pole_id
OPTIONS (
  description = '5-minute demand response baselines per pole'
);

-- ============================================================================
-- Voltage Events Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS `PROJECT_ID.smart_grid_analytics.voltage_events` (
  event_id STRING NOT NULL,
  meter_id STRING NOT NULL,
  pole_id STRING NOT NULL,
  event_type STRING NOT NULL,  -- 'sag' or 'swell'
  severity STRING NOT NULL,    -- 'minor', 'warning', 'critical'
  event_start TIMESTAMP NOT NULL,
  event_end TIMESTAMP,
  duration_seconds INT64,
  min_voltage_v FLOAT64,
  max_voltage_v FLOAT64,
  avg_voltage_v FLOAT64,
  reading_count INT64,
  detected_at TIMESTAMP
)
PARTITION BY DATE(event_start)
CLUSTER BY pole_id, meter_id
OPTIONS (
  description = 'Detected voltage anomaly events'
);
