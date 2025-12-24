# AMI 2.0 Smart Meter Analytics - Assumptions and Data Model

## Overview

This document defines the data model, scaling assumptions, and configuration parameters for the AMI 2.0 smart meter analytics tutorial.

## AMI 2.0 vs. Legacy AMI Comparison

| Parameter | Legacy AMI | AMI 2.0 |
|-----------|-----------|---------|
| Sampling Interval | 5-60 minutes | 1 second (or faster) |
| Data per meter/day | ~288-1,440 readings | 86,400 readings |
| Primary Use Case | Billing, basic load analysis | Real-time grid monitoring, DR, anomaly detection |
| Data Volume Multiplier | 1x (baseline) | 50M x (vs 15-min intervals) |

## Data Model

### Telemetry Event Schema

Each telemetry message represents a single point-in-time measurement from one meter.

```json
{
  "event_ts": "2025-12-23T08:00:01.000Z",
  "meter_id": "m_poleA_0007",
  "pole_id": "poleA",
  "seq": 123456,
  "voltage_v": 236.8,
  "current_a": 4.91,
  "power_kw": 1.10,
  "reactive_kvar": 0.25,
  "freq_hz": 60.02,
  "quality_flags": []
}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_ts` | string (RFC3339) | Yes | Event timestamp in UTC |
| `meter_id` | string | Yes | Unique meter identifier |
| `pole_id` | string | Yes | Pole/gateway aggregation point |
| `seq` | integer | Yes | Monotonically increasing sequence number per meter |
| `voltage_v` | float | Yes | RMS voltage in volts |
| `current_a` | float | Yes | RMS current in amperes |
| `power_kw` | float | Yes | Active power in kilowatts |
| `reactive_kvar` | float | No | Reactive power in kVAR |
| `freq_hz` | float | No | System frequency in Hz |
| `quality_flags` | array[string] | No | Data quality indicators |

### Quality Flags

- `estimated` - Value was interpolated/estimated
- `missing` - Original sample was missing
- `out_of_range` - Value outside expected bounds
- `voltage_sag` - Voltage below threshold
- `voltage_swell` - Voltage above threshold

## Scaling Parameters

### Default Configuration (Tutorial)

| Parameter | Value | Notes |
|-----------|-------|-------|
| Meters per pole | 10 | Typical residential pole |
| Poles per simulation | 1-5 | Tutorial scale |
| Sampling rate | 1 Hz | One reading per second |
| Messages per second | 10-50 | Tutorial throughput |
| Data retention | 7 days | Tutorial storage |

### Production-Scale Reference

| Parameter | Value | Notes |
|-----------|-------|-------|
| Meters per pole | 10-50 | Varies by deployment |
| Poles per region | 1,000-100,000 | Medium utility |
| Total meters | 100,000-5,000,000 | Range of utility sizes |
| Messages per second | 100K-5M | At 1 Hz sampling |
| Daily data volume | 100 GB - 5 TB | Depending on scale |

## Electrical Parameters

### Voltage Model

- **Nominal Voltage**: 240V (split-phase residential) or 120V (single-phase)
- **Normal Range**: ±5% of nominal (228V-252V for 240V nominal)
- **Voltage Sag Threshold**: <220V (for anomaly detection)
- **Voltage Swell Threshold**: >260V
- **Noise Standard Deviation**: 2-5V

### Power Model

Daily load curve follows typical residential pattern:
- **Base Load**: 0.5-1.0 kW (appliances, standby)
- **Morning Peak**: 6:00-9:00 AM (1.5-3.0 kW)
- **Midday Valley**: 10:00 AM - 4:00 PM (0.8-1.5 kW)
- **Evening Peak**: 5:00-9:00 PM (2.0-5.0 kW)
- **Night Valley**: 10:00 PM - 5:00 AM (0.3-0.8 kW)

### Power Factor

- **Typical Range**: 0.85-0.99
- **Default**: 0.95 (lagging)
- **Reactive Power**: Q = P × tan(acos(PF))

## Network Backhaul Profiles

| Profile | Latency (ms) | Jitter (ms) | Drop Rate |
|---------|-------------|-------------|-----------|
| Wired | 5-30 | ±10 | 0.01% |
| 5G | 20-200 | ±50 | 0.1% |
| LTE-M | 50-300 | ±100 | 0.5% |
| Satellite | 300-900 | ±200 | 1.0% |

## Storage Strategy

### Raw Archive (Cloud Storage)

Path structure:
```
gs://{bucket}/raw/pole_id={pole}/dt={YYYY-MM-DD}/hr={HH}/min={MM}/*.jsonl
```

- Files written every 1-5 minutes
- JSONL format (one JSON object per line)
- Compressed with gzip

### BigQuery Tables

**Primary Table**: `raw_meter_readings`
- Partitioned by: `DATE(event_ts)`
- Clustered by: `pole_id`, `meter_id`
- Partition expiration: 90 days (configurable)

**Aggregated Tables** (optional):
- `minute_agg_pole`: Per-minute pole aggregates
- `dr_5min_baseline`: 5-minute DR baseline data

## Analytics Thresholds

### Voltage Anomaly Detection

| Condition | Threshold | Duration |
|-----------|-----------|----------|
| Voltage Sag (Alert) | < 220V | ≥ 5 seconds |
| Voltage Sag (Critical) | < 200V | ≥ 3 seconds |
| Voltage Swell (Alert) | > 260V | ≥ 5 seconds |

### Demand Response

| Parameter | Value |
|-----------|-------|
| Baseline Window | 5 minutes |
| Similar Day Count | 5-10 days |
| Adjustment Factor | Weather-normalized (optional) |
| Event Window | 1-4 hours |

## Cost Considerations

### Estimated Costs (Tutorial Scale)

| Service | Usage | Estimated Cost |
|---------|-------|----------------|
| Pub/Sub | 10 msg/s, 24 hours | < $1 |
| Dataflow | 1 worker, 4 hours | ~$0.50 |
| BigQuery | 1 GB storage | < $0.05 |
| Cloud Storage | 1 GB | < $0.03 |
| **Total (4-hour demo)** | | **~$2-5** |

### Cost Control Recommendations

1. Use small worker counts for Dataflow (`--max_num_workers 2`)
2. Run demo for limited time windows
3. Clean up resources after demo
4. Use partition expiration for automatic data cleanup
5. Monitor usage with Cloud Billing alerts
