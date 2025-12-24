# Analytics SQL Scripts

This directory contains SQL scripts for analyzing AMI 2.0 smart meter data in BigQuery.

## Scripts

### voltage_anomaly.sql
Detects voltage sag events where voltage stays below threshold for consecutive seconds.
- Identifies meters with sustained low voltage
- Uses gap-and-island technique for sessionization
- Outputs event start/end times and duration

### dr_baseline_5min.sql
Computes 5-minute demand response baselines per pole.
- Aggregates seconds-level data to 5-minute intervals
- Calculates baseline from historical similar periods
- Provides baseline for DR event performance measurement

### feeder_health_summary.sql
Generates health summary metrics per pole.
- Voltage quality statistics
- Power consumption patterns
- Data quality metrics (missing readings, gaps)

### bq_tables.sql
Optional DDL statements for creating tables if not using Terraform.

## Usage

Run these queries in the BigQuery console or via `bq query`:

```bash
# Run voltage anomaly detection
bq query --use_legacy_sql=false < voltage_anomaly.sql

# Compute DR baseline
bq query --use_legacy_sql=false < dr_baseline_5min.sql
```

## Scheduling

These queries can be scheduled using:
1. **BigQuery Scheduled Queries** - Built-in scheduling in BigQuery
2. **Cloud Scheduler + Cloud Run** - For more complex workflows

See the main README for scheduling setup instructions.
