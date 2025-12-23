# Next-Gen AMI (AMI 2.0) Smart Meter Analytics on Google Cloud
Implementation Plan for IEEE-PES TF Cloud4PowerGrid Tutorial

## 0) Scope, Goals, Non-Goals

### Goal
Build a realistic, cloud-native reference tutorial that demonstrates **seconds-level AMI 2.0 meter analytics** end-to-end:
- Simulated AMI 2.0 meters → pole/relay gateway → backhaul (5G/satellite/wired) → cloud ingestion
- Durable raw storage (JSON/CSV) + queryable database
- Periodic + on-demand analytics for **non-intrusive node monitoring** (voltage quality / anomaly detection) and **demand response (DR) insights** (baseline + event performance features)

### Non-Goals (for v1)
- Not implementing proprietary AMI head-end protocols (DLMS/COSEM, ANSI C12.x) end-to-end
- Not doing distribution state estimation or full power-flow (can be a v2 extension)
- Not implementing utility-grade security compliance (but use realistic least-privilege IAM + TLS)

### Key “Realism” Requirements
- **Seconds-level resolution** (e.g., 1 Hz, configurable), explicitly contrasting with legacy 5/15/60-min intervals
- Pole/relay aggregation and backhaul effects: batching, jitter, drops, retries, reordering
- Cloud architecture reflecting post-IoT-Core era (direct-to-Pub/Sub pattern)

---

## 1) High-Level Architecture

### Logical Data Flow
1. **Edge (Meters)**
   - Multiple “meters” generate per-second measurements
2. **Pole / Relay Gateway**
   - Aggregates meters at a pole
   - Batches & publishes to cloud over simulated backhaul (5G/sat/wired)
3. **Cloud Ingestion**
   - Pub/Sub topic receives telemetry events
4. **Stream Processing**
   - Dataflow streaming pipeline validates, normalizes, and writes:
     - **Raw archive** (GCS as JSON/CSV “data lake”)
     - **Warehouse** (BigQuery partitioned tables)
5. **Analytics**
   - Periodic (Cloud Scheduler → BigQuery scheduled query / Cloud Run job)
   - On-demand (HTTP endpoint → query BigQuery → return results)
6. **Outputs**
   - Voltage quality insights, anomaly flags, DR baseline aggregates

### Why these services
- **Pub/Sub**: decouples producers/consumers; absorbs bursts; supports at-least-once delivery.
- **Dataflow (Beam)**: standard GCP streaming ETL.
- **GCS**: cheap durable raw storage (JSON/CSV) for reprocessing / audit.
- **BigQuery**: time-partitioned, scalable analytics for seconds-level data.
- **Cloud Run + Scheduler**: simplest tutorial-friendly “periodic + on-demand” compute.

---

## 2) Repo Placement and Directory Structure

Target repo: `IEEE-PES-TF-Cloud4PowerGrid/cloud_adoption_tutorials`

Create a new tutorial folder:
`cloud_adoption_tutorials/ami_meter/`

```text
cloud_adoption_tutorials/
└── ami_meter/
    ├── plan_v1.md
    ├── README.md
    ├── architecture/
    │   ├── diagram.mmd                 # Mermaid diagram (generated)
    │   └── assumptions.md              # data model + scaling knobs
    ├── infrastructure/
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── outputs.tf
    │   └── versions.tf
    ├── edge_simulation/
    │   ├── requirements.txt
    │   ├── config.yaml
    │   ├── simulator.py                # meter data generator
    │   ├── gateway_relay.py             # pole/relay publisher
    │   └── schemas/
    │       └── telemetry.schema.json
    ├── cloud_processing/
    │   ├── requirements.txt
    │   ├── setup.py
    │   ├── streaming_pipeline.py        # Pub/Sub -> (GCS + BQ)
    │   └── transforms.py                # parse/validate/enrich
    ├── analytics/
    │   ├── bq_tables.sql                # optional (if not created by TF)
    │   ├── voltage_anomaly.sql
    │   ├── dr_baseline_5min.sql
    │   ├── feeder_health_summary.sql
    │   └── README.md
    ├── services/
    │   ├── api/
    │   │   ├── main.py                  # Cloud Run API (FastAPI/Flask)
    │   │   ├── requirements.txt
    │   │   └── Dockerfile
    │   └── jobs/
    │       ├── periodic_job.py          # optional Cloud Run job
    │       └── requirements.txt
    └── scripts/
        ├── 00_prereq.sh
        ├── 10_deploy_tf.sh
        ├── 20_run_edge_vm.sh
        ├── 30_launch_dataflow.sh
        ├── 40_run_queries.sh
        └── 90_cleanup.sh
```
## 3) Data Model (Seconds-Level AMI 2.0 Telemetry)

### Event Granularity
-	Default: 1 Hz per meter (configurable)
-	Design must support scale knobs (meters per pole, poles per region, Hz)

### Telemetry Event Schema (JSON)

Each Pub/Sub message contains **one reading** (simplest) OR **a batch** (more realistic).
For v1: publish **one reading per message**; batching handled by Pub/Sub client batcher.
(Optionally add “batch message” mode as a config switch.)

Required fields:
-	```event_ts``` (RFC3339 UTC string)
-	```meter_id``` (string)
-	```pole_id``` (string)
-	```seq``` (int) monotonically increasing per meter (helps ordering checks)
-	```voltage_v``` (float) RMS
-	```current_a``` (float) RMS
-	```power_kw``` (float) active power
-	```reactive_kvar``` (float) optional
-	```freq_hz``` (float) optional
-	```quality_flags``` (array/string) optional (missing sample, estimated, etc.)

Example:
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

### Storage Strategy
-	Raw archive (GCS):
-	JSON Lines per minute or per 5 minutes per pole: ```gs://.../raw/pole_id=.../dt=YYYY-MM-DD/hr=HH/min=MM/*.jsonl```
-	Optional CSV exports for “business analyst friendly” usage: ```gs://.../csv/.../*.csv```
-	BigQuery:
-	Table ```raw_meter_readings``` partitioned by DATE(event_ts)
-	Cluster by ```pole_id, meter_id```

⸻

## 4) Infrastructure (Terraform) — Detailed Requirements

### Variables
-	```project_id, region```
-	```artifact_bucket_name```
-	```bq_dataset```
-	```pubsub_topic, pubsub_subscription```
-	optional: ```enable_dead_letter, dlq_topic, max_delivery_attempts```

### Resources to Create
1.	GCS buckets
-	```ami-artifacts-```... (Dataflow temp/staging)
-	```ami-raw-archive-```... (JSON/CSV lake)
2.	Pub/Sub
-	Topic: ```ami-meter-data```
-	Subscription: ```ami-meter-data-sub``` (pull for Dataflow)
-	Recommended settings:
  -	ack deadline 20–60s (Dataflow default is fine)
  -	message retention 1 day (dev), configurable
  -	Dead letter topic (optional): ```ami-meter-data-dlq```
3.	BigQuery
-	Dataset: ```smart_grid_analytics```
-	Tables:
  -	```raw_meter_readings``` (partitioned by day on event_ts, clustered)
  -	```minute_agg_pole``` (optional materialized table)
  -	```dr_5min_baseline``` (optional materialized table)
4.	IAM / Service Accounts
-	```edge-device-sa```:
  -	```roles/pubsub.publisher``` on topic
-	```dataflow-sa```:
  -	```roles/dataflow.worker```
  -	```roles/pubsub.subscriber``` on subscription
  -	```roles/bigquery.dataEditor``` on dataset
  -	```roles/storage.objectAdmin``` on raw archive bucket (or narrower write role)
-	```api-sa``` (Cloud Run API):
  -	```roles/bigquery.jobUser```
  -	```roles/bigquery.dataViewer``` on dataset
5.	(Optional) Compute Engine VM (edge gateway)
-	Minimal machine type (e.g., ```e2-small```)
-	Startup script can install Python deps and run gateway (nice demo)
-	Attach ```edge-device-sa```

### Terraform Outputs
-	Topic name, subscription name
-	Raw archive bucket URI
-	BigQuery dataset/table IDs
-	Service account emails

⸻

## 5) Edge Simulation Implementation (VM or Local)

### ```edge_simulation/config.yaml```

Must include:
-	```pole_id```
-	```num_meters```
-	```sample_hz```
-	```publish_mode``` (single|batch)
-	```network_profile``` (wired|5g|sat)
-	```jitter_ms_range, drop_prob, reorder_prob```
-	```voltage_nominal, voltage_sag_prob, voltage_sag_depth```
-	```load_profile``` (daily curve params)
-	```pubsub_topic```

### ```simulator.py``` (Meter Generator)

Core logic:
-	For each meter, maintain:
  -	seq counter
  -	baseline load curve (time-of-day)
  -	random walk noise + occasional spikes
-	Emit events at ```sample_hz```
-	Voltage model (simple but realistic):
  -	nominal ± gaussian noise
  -	sag events: drop below threshold for N seconds
-	Power model:
  -	```power_kw = base_curve(t) * meter_factor + noise```
-	Reactive power (optional):
  -	```reactive_kvar = power_kw * tan(acos(pf))``` with pf ~ 0.95–0.99
-	Provide CLI args:
  -	```--config edge_simulation/config.yaml```
  -	```--stdout``` (print events) for debugging

Acceptance criteria:
-	Can generate ≥ 10 meters @ 1Hz reliably on laptop/VM
-	Injects at least one voltage sag every configurable interval for demo

### ```gateway_relay.py``` (Pole Gateway Publisher)

Responsibilities:
-	Read from simulator generator/queue
-	Add gateway metadata:
  -	```gateway_id, network_profile```
  -	ingestion timestamp ```gateway_ingest_ts``` (optional)
-	Simulate backhaul:
  -	jitter sleep based on profile:
    -	wired: 5–30ms
    -	5G: 20–200ms
    -	sat: 300–900ms
    -	random drops (drop_prob), reorders (reorder_prob) by holding a small buffer
-	Publish to Pub/Sub:
  -	Use Pub/Sub Python client with batching:
    -	```max_messages``` ~ 100–500
    -	```max_latency``` ~ 0.2–1.0s
  -	Include message attributes:
    -	```pole_id, meter_id``` (optional; helpful for filters)
-	Retries:
  -	on publish failure, retry with exponential backoff (bounded)
-	Observability:
  -	log published msg count/sec, dropped, retry count

Acceptance criteria:
-	Publishing throughput stable at:
  -	10 meters @ 1Hz (10 msg/s)
  -	100 meters @ 1Hz (100 msg/s) (optional stress mode)

⸻

## 6) Cloud Processing (Dataflow / Apache Beam)

### Pipeline: ```streaming_pipeline.py```

Inputs:
-	```--input_subscription```
-	```--output_bq_table```
-	```--raw_archive_bucket``` (GCS)
-	```--raw_archive_prefix``` default ```raw/```
-	```--dlq_topic``` optional
-	```--window_seconds``` optional (0 means no aggregation)

Steps (must be explicit in code):
  1.	Read from Pub/Sub (```ReadFromPubSub(with_attributes=True)```)
	2.	Decode bytes → JSON parse
	3.	Validate schema:
    -	required keys present
    -	parse RFC3339 timestamp to ```datetime```
    -	numeric fields are floatable
	4.	Enrich:
    -	add ```ingest_ts``` (Dataflow processing time)
    -	add ```event_date``` for partition helpers (optional)
	5.	Write raw archive:
    -	JSONL write to GCS with windowed file naming (e.g., 1-minute files)
	6.	Write to BigQuery:
    -	Streaming inserts into partitioned ```raw_meter_readings```
	7.	DLQ behavior:
    -	If parse/validate fails:
    -	write bad record to DLQ Pub/Sub topic OR to ```gs://.../deadletter/...```
    -	include error reason and original payload

Optional streaming aggregation (demo mode):
-	If ```--window_seconds=60```:
  -	key by ```pole_id```
  -	compute mean/min/max voltage, total kW per pole per minute
  -	write to ```minute_agg_pole```

Dataflow runner settings for tutorial:
-	```--runner``` DataflowRunner
-	```--region us-central1``` (example)
-	```--worker_machine_type n1-standard-2``` (or ```e2-standard-2```)
-	```--max_num_workers 2``` (keep cost low)
-	```--streaming```

Acceptance criteria:
-	End-to-end latency (edge publish → BQ row visible) typically seconds to <1 minute
-	Raw archive files appear in GCS within a few minutes
-	DLQ receives malformed messages (test with injected bad payloads)

⸻

## 7) BigQuery Schema and Table Design

### Table: ```smart_grid_analytics.raw_meter_readings```
-	Partition: ```DATE(event_ts)```
-	Cluster: ```pole_id, meter_id```
-	Columns:
  -	```event_ts TIMESTAMP```
  -	```ingest_ts TIMESTAMP```
  -	```meter_id STRING```
  -	```pole_id STRING```
  -	```seq INT64```
  -	```voltage_v FLOAT64```
  -	```current_a FLOAT64```
  -	```power_kw FLOAT64```
  -	```reactive_kvar FLOAT64```
  -	```freq_hz FLOAT64```
  -	```quality_flags ARRAY<STRING>```
  -	```network_profile STRING```

### Derived Tables / Views (recommended)
-	View ```v_5min_pole``` (5-min aggregates)
-	Table ```dr_5min_baseline``` (materialized baseline for DR periods)
-	Table ```voltage_events``` (anomaly events, one row per detected incident)

⸻

## 8) Analytics (Periodic + On-Demand)

### A) Non-Intrusive Monitoring: Voltage Sag / Violation

```analytics/voltage_anomaly.sql```

Definition (tutorial-friendly):
-	Sag event when ```voltage_v < 220``` for ≥ 5 consecutive seconds (per meter)
Outputs:
-	```meter_id, pole_id, start_ts, end_ts, min_voltage, duration_s```

Implementation approach:
-	Use sessionization / gaps-and-islands on per-meter low-voltage sequences.

### B) DR Baseline Features (5-Minute)

```analytics/dr_baseline_5min.sql```

Compute:
-	5-minute average kW per pole (or per meter)
-	Baseline candidates:
  -	simple historical average per same time-of-day
  -	rolling median of last N similar days (optional)
Outputs:
-	baseline_kW, actual_kW during an “event window”, estimated shed

### C) Feeder / Pole Health Summary (Operator dashboard)

```analytics/feeder_health_summary.sql```
Per pole per hour/day:
-	percent low-voltage samples
-	peak kW
-	volatility metric (std dev of voltage)
-	missing data rate (seq gaps)

⸻

## 9) Serving Results: On-Demand API (Cloud Run)

Implement ```services/api/main.py```:
-	Endpoint ```GET /health```
-	Endpoint ```GET /pole/{pole_id}/summary?start=...&end=...```
-	Endpoint ```GET /anomalies?start=...&end=...```
-	Endpoint ```POST /dr/compute``` with JSON body describing event window

Implementation details:
-	Use BigQuery client library
-	Parameterized queries only (avoid SQL injection)
-	Return JSON responses suitable for demos

⸻

## 10) Scheduling Periodic Analytics

Two simple options (pick one for v1; document both):

### Option 1 (simplest): BigQuery Scheduled Queries
-	Schedule dr_baseline_5min.sql hourly
-	Schedule voltage_anomaly.sql every 5 minutes

### Option 2: Cloud Scheduler → Cloud Run Job
-	Scheduler triggers a job that runs SQL and writes to output tables

⸻

## 11) README Tutorial Flow (What attendees do)

```README.md``` must include step-by-step commands:
1.	Prereqs:
-	```gcloud, terraform, python3, pip```
2.	Auth:
-	```gcloud auth login```
-	```gcloud config set project ...```
3.	Deploy infra:
-	```cd infrastructure && terraform init && terraform apply```
4.	Run edge:
-	local: ```python edge_simulation/gateway_relay.py --config ...```
-	or VM: SSH and run same command
5.	Launch Dataflow:
-	python ```cloud_processing/streaming_pipeline.py --runner DataflowRunner ...```
6.	Validate:
-	query BigQuery ```raw_meter_readings``` (sample SQL)
7.	Run analytics:
-	run provided SQL scripts
8.	On-demand API:
-	deploy Cloud Run, call endpoints, show results
9.	Cleanup:
-	cancel Dataflow job
-	delete Cloud Run service
-	```terraform destroy```

Include a “cost guardrails” section:
-	keep worker counts small
-	delete resources after demo
-	note that seconds-level data can be large; use short demo windows

⸻

## 12) Testing, QA, and Demo Checklist

### Unit Tests (minimum)
-	JSON schema validation tests
-	timestamp parsing tests
-	backhaul simulation determinism with fixed seed

### Integration Tests
-	“smoke test” mode:
-	2 meters, 1 pole, 1Hz, run 2 minutes
-	assert:
-	Pub/Sub receives messages
-	BigQuery row count increases
-	One sag anomaly detected if configured

### Demo Script
-	Show architecture diagram
-	Start simulator
-	Show Pub/Sub topic metrics (messages/sec)
-	Show BigQuery raw table partitions
-	Run anomaly query and display event
-	Show DR 5-minute baseline aggregate chart/table
-	Call API endpoint to fetch summary

⸻

## 13) Implementation Milestones (for a coding agent)

M1 — Infra complete:
-	Terraform creates Pub/Sub, GCS, BigQuery, service accounts

M2 — Edge simulation complete:
-	simulator produces valid JSON events
-	gateway publishes to Pub/Sub with jitter + batching

M3 — Dataflow pipeline complete:
-	reads from Pub/Sub
-	writes raw to GCS + structured to BigQuery
-	DLQ handles invalid events

M4 — Analytics complete:
-	voltage anomaly query
-	DR 5-minute aggregation query
-	health summary query

M5 — Tutorial polish:
-	README runnable end-to-end
-	cleanup script
-	screenshots / expected outputs

⸻

## 14) References (optional reading links)
-	Pub/Sub: https://cloud.google.com/pubsub
-	Dataflow / Beam: https://cloud.google.com/dataflow
-	BigQuery partitioning: https://cloud.google.com/bigquery/docs/partitioned-tables
-	Cloud Run: https://cloud.google.com/run
-	Cloud Scheduler: https://cloud.google.com/scheduler
-	IoT Core retirement (background): search “Cloud IoT Core retired Aug 16 2023”
-	Smart meter communications overview (background): search “smart meter MQTT LTE-M NB-IoT”