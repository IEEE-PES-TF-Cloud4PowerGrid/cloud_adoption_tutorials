# Next‑Gen AMI Analytics with Google Cloud - Detailed Implementation Plan

## Purpose and Audience

This tutorial is intended for the IEEE PES Working Group on Cloud for Power Grid. It demonstrates how to ingest, store and analyse high‑frequency data from second‑generation Advanced Metering Infrastructure (AMI 2.0) meters using **Google Cloud** services. Unlike earlier AMI deployments that measure consumption every 5-15 minutes, AMI 2.0 devices can sample voltages and currents tens of thousands of times per second and produce data **one‑second or better**[\[1\]](https://sense.com/wp-content/uploads/2024/05/AMI-2.0-Buyers-Guide.pdf#:~:text=Today%20we%20have%20AMI%202,vegetation%20hitting%20power%20lines%2C%20etc). A high‑fidelity stream allows utilities to detect grid anomalies and support fast demand response programs, but it also generates **orders of magnitude more data** (50 million times more than 15 minute intervals[\[1\]](https://sense.com/wp-content/uploads/2024/05/AMI-2.0-Buyers-Guide.pdf#:~:text=Today%20we%20have%20AMI%202,vegetation%20hitting%20power%20lines%2C%20etc)). This plan outlines how to build a realistic, cloud‑native pipeline that handles this data volume, provides non‑intrusive monitoring and computes demand response (DR) baselines.

### Why Direct‑to‑Pub/Sub

Google retired its Cloud IoT Core service on **August 16 2023**[\[2\]](https://www.emqx.com/en/blog/why-emqx-is-your-best-google-cloud-iot-core-alternative#:~:text=Future%20of%20Google%20Cloud%20for,Shutdown%20of%20Google%20IoT%20Core)[\[3\]](https://blog.balena.io/gcp-iot-core-retirement-migration-to-balena/#:~:text=The%20announcement%20for%20the%20end,discontinued%20on%20August%2016th%2C%202023). Instead of registering devices in IoT Core, the recommended pattern is to publish directly to **Cloud Pub/Sub** using the MQTT or HTTP protocols. Cloud Pub/Sub is a **global, cloud‑based messaging framework** that decouples senders and receivers and provides reliable asynchronous communication[\[4\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=Google%20Cloud%20Pub%2FSub%20is%20a,cases%20for%20your%20%2067). Pub/Sub topics accept messages from anywhere in the world and store them redundantly across multiple availability zones to guarantee _at‑least‑once_ delivery[\[5\]\[6\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=%2A%20). It can automatically scale from **10 000 messages per second to millions**[\[7\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=%2A%20), making it suitable for high‑frequency smart‑meter data streams. Pub/Sub supports event‑driven architecture patterns, allowing Dataflow or other services to subscribe and process events independently[\[8\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=%2A%20%23%23%23%20Event).

### AMI 2.0 and Communication Requirements

Modern smart meters embed microcontrollers that sample waveforms at **15 000 samples per second** with 16‑bit quantisation for current and 14‑bit for voltage[\[1\]](https://sense.com/wp-content/uploads/2024/05/AMI-2.0-Buyers-Guide.pdf#:~:text=Today%20we%20have%20AMI%202,vegetation%20hitting%20power%20lines%2C%20etc). These devices can detect sags, swells and harmonics on the distribution network. AMI 2.0 meter gateways typically transmit data via **cellular IoT** (2G, 3G, 4G, 5G, LTE‑M or NB‑IoT) or wired backhaul. A SIM‑equipped gateway can push measurements over a 5G network to the cloud, providing good indoor penetration and high maximum coupling loss[\[9\]](https://www.emnify.com/blog/how-smart-meters-communicate#:~:text=Cellular%20). Regulators and vendors are pushing for **near real‑time data availability**[\[10\]](https://www.emnify.com/blog/how-smart-meters-communicate#:~:text=While%20smart%20meters%20didn%E2%80%99t%20require,more%20frequently%20from%20more%20places), so the demo should reflect seconds‑level latency. MQTT is a widely used protocol in IoT because its publish/subscribe model is lightweight and suits constrained devices[\[11\]](https://www.emnify.com/blog/how-smart-meters-communicate#:~:text=Smart%20meters%20that%20use%20cellular,transport%20data%20to%20the%20cloud).

## Overview of the Architecture

The demonstration consists of four logical layers:

- **Edge / Simulation Layer - "Power Pole"**
  - A Compute Engine VM acts as an edge gateway representing the distribution pole that aggregates data from multiple meters. It runs two Python programs:
  - **simulator.py** generates synthetic one‑second AMI 2.0 data for multiple meter_ids. Voltage, current and power vary according to daily load curves, with occasional dips injected to test anomaly detection.
  - **gateway_relay.py** batches these readings and publishes them to a Pub/Sub topic using the Python Pub/Sub client. Batching and a random sleep simulate variable latency on a 5G or satellite link.
- **Ingestion Layer - Pub/Sub**
  - A Pub/Sub **topic** (ami‑meter‑data) and **subscription** (ami‑meter‑data‑sub) act as a decoupling buffer between the edge and downstream analytics. Publishers and subscribers do not need to know about each other, which simplifies scaling and fault isolation[\[4\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=Google%20Cloud%20Pub%2FSub%20is%20a,cases%20for%20your%20%2067). Messages are stored on multiple servers for durability[\[6\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=%2A%20).
- **Processing Layer - Dataflow (Apache Beam)**
  - A **streaming Dataflow job** reads messages from the subscription, parses JSON records, optionally applies fixed windows and aggregations, and writes rows into BigQuery. Dataflow's pipeline model uses PCollections and PTransforms to process unbounded streams[\[12\]](https://medium.com/codex/a-dataflow-journey-from-pubsub-to-bigquery-68eb3270c93#:~:text=The%20Pipeline%20object%20is%20formed,PCollections%20and%20outputs%20some%20more). Streaming jobs require a minimum worker type such as **n1‑standard‑2**[\[13\]](https://medium.com/codex/a-dataflow-journey-from-pubsub-to-bigquery-68eb3270c93#:~:text=You%E2%80%99ll%20notice%20how%20we%20simply,%E2%80%9D).
- **Storage / Analytics Layer - BigQuery**
  - A **BigQuery dataset** (smart_grid_analytics) stores raw and aggregated data. A table raw_meter_readings is partitioned by day on the event_timestamp column. Time‑based partitions significantly reduce query costs and improve retrieval efficiency for one‑second data[\[14\]\[15\]](https://moldstud.com/articles/p-effective-partitioning-strategies-for-real-time-data-processing-in-bigquery#:~:text=Analyzing%20data%20that%20arrives%20every,bytes%2C%20directly%20lowering%20operational%20expenses). Additional views and scheduled queries compute 5‑minute aggregates for demand response and detect voltage anomalies.

The following diagram summarises the flow:

AMI 2.0 meters (1Hz data) → Power Pole VM (simulator & gateway) →  
5G/Wired/Satellite uplink → Pub/Sub Topic → Dataflow → BigQuery

## Project Directory Structure

Create a new repository folder ami‑smart‑meter‑demo/ with the following layout. The coding agent should adhere to this structure when generating code:

ami‑smart‑meter‑demo/  
├── README.md # Explanation of architecture, setup, and cleanup instructions  
├── infrastructure/ # Terraform files for provisioning GCP resources  
│ ├── main.tf  
│ ├── variables.tf  
│ └── outputs.tf  
├── edge_simulation/  
│ ├── requirements.txt # Python dependencies (e.g., numpy, google-cloud-pubsub)  
│ ├── simulator.py # Generates synthetic 1Hz AMI data  
│ └── gateway_relay.py # Publishes batched messages to Pub/Sub  
├── cloud_processing/  
│ ├── requirements.txt # Apache Beam, google-cloud-bigquery, google-cloud-pubsub  
│ ├── setup.py # Packaging metadata for Dataflow pipeline  
│ └── streaming_pipeline.py # Dataflow/Apache Beam pipeline  
└── analytics/  
├── voltage_anomaly.sql # SQL to detect sustained voltage dips  
└── dr_baseline.sql # SQL to compute 5‑minute DR baselines

## Step‑by‑Step Implementation

### 1\. Infrastructure Provisioning (Terraform)

The infrastructure/ directory uses Terraform to declaratively create the GCP resources. Use the Google provider and supply variables for the project ID and region. The resources include:

- **Pub/Sub Topic (ami‑meter‑data)** and **Subscription (ami‑meter‑data‑sub)**.
- Configure the subscription as a **pull** subscription because Dataflow will pull messages.
- Optionally enable message retention for at least one day so data is available during development.
- **BigQuery Dataset (smart_grid_analytics)**.
- **BigQuery Table (raw_meter_readings)** with the following schema: | Field | Type | Description | |-------------------|-----------|-------------------------------------------------| | event_timestamp | TIMESTAMP| event time of the reading | | meter_id | STRING | unique ID of the smart meter | | pole_id | STRING | ID of the aggregation pole/gateway | | voltage_v | FLOAT | RMS voltage in volts | | current_a | FLOAT | RMS current in amperes | | power_kw | FLOAT | active power in kW |
- Use **time partitioning**: partition by day on event_timestamp to reduce cost and improve query efficiency for high‑frequency data[\[14\]](https://moldstud.com/articles/p-effective-partitioning-strategies-for-real-time-data-processing-in-bigquery#:~:text=Analyzing%20data%20that%20arrives%20every,bytes%2C%20directly%20lowering%20operational%20expenses).
- Optionally enable **clustering** on meter_id and pole_id for faster queries.
- **Service Accounts** with least‑privilege IAM roles:
- edge‑device‑sa - assign roles/pubsub.publisher to allow publishing to the topic.
- dataflow‑sa - assign roles/dataflow.worker, roles/pubsub.subscriber, and roles/bigquery.dataEditor so the pipeline can pull messages and write to BigQuery.
- **Compute Engine VM** (optional, can also run locally). Use a small machine type (e.g., e2‑micro for simulation) with Cloud SDK installed. Attach the edge‑device‑sa service account.

**Outputs**: Provide outputs for topic name, subscription name, BigQuery dataset ID and table ID so that later modules can reference them.

### 2\. Edge Simulation (Power Pole)

The edge_simulation/ folder contains code that runs on the VM to simulate AMI 2.0 data.

#### simulator.py

- Define parameters such as NUM_METERS_PER_POLE, POLE_ID, BASE_VOLTAGE, and NOISE_STD. Use numpy to generate sinusoidal loads and random noise.
- Create a loop that iterates once per second. For each meter, compute:
- Voltage (voltage_v): baseline (e.g., 240 V) ± random noise and occasional dips below 220 V to simulate voltage sags.
- Current (current_a): derived from power or random variation.
- Power (power_kw): based on a daily load curve (morning and evening peaks) and per‑meter variability.
- Produce a JSON object for each meter with keys meter_id, pole_id, timestamp (ISO 8601), voltage_v, current_a, and power_kw. Convert the timestamp to UTC to align with BigQuery.
- Write log statements to stdout so the user can observe the simulation.

#### gateway_relay.py

- Initialise a PublisherClient from google.cloud.pubsub_v1 using the credentials of edge‑device‑sa.
- Configure batching settings (e.g., max_messages=100, max_latency=1) to simulate network backhaul and reduce overhead.
- In a loop, call the simulator to get the latest batch of JSON records and publish them to the Pub/Sub topic. Encode each message as UTF‑8 and include attributes such as meter_id for potential filtering.
- Randomly sleep (e.g., 0.1-0.5 s) between publishes to emulate network jitter on a 5G/Satellite link[\[9\]](https://www.emnify.com/blog/how-smart-meters-communicate#:~:text=Cellular%20).

### 3\. Cloud Processing Pipeline (Dataflow)

The cloud_processing/streaming_pipeline.py implements an Apache Beam pipeline. It should:

- **Read from Pub/Sub** using beam.io.ReadFromPubSub with the subscription name.
- **Decode and parse JSON**: apply a beam.Map to parse each message into a Python dict and convert the ISO timestamp string to a Python datetime object.
- **Attach an ingestion timestamp** (optional) for debugging.
- **(Optional) Windowing**: If you want to demonstrate real‑time aggregation (e.g., compute per‑minute averages), add beam.WindowInto with FixedWindows(60) and use beam.CombinePerKey to compute the mean voltage/current. Dataflow uses PCollections and windowing to process unbounded streams[\[12\]](https://medium.com/codex/a-dataflow-journey-from-pubsub-to-bigquery-68eb3270c93#:~:text=The%20Pipeline%20object%20is%20formed,PCollections%20and%20outputs%20some%20more). However, for raw ingestion, skip windowing and write records directly.
- **Write to BigQuery** using beam.io.WriteToBigQuery in **streaming inserts** mode. Provide the table schema, specify time partitioning (already defined by Terraform), and set write disposition to WRITE_APPEND. Use the dataflow‑sa service account for authentication.

When deploying the pipeline via the Cloud SDK, specify the project ID, region, input subscription, output table, and machine type. Streaming pipelines require at least an n1‑standard‑2 machine type according to Dataflow best practices[\[13\]](https://medium.com/codex/a-dataflow-journey-from-pubsub-to-bigquery-68eb3270c93#:~:text=You%E2%80%99ll%20notice%20how%20we%20simply,%E2%80%9D).

### 4\. Analytics and Demonstrations

The analytics/ directory contains SQL scripts to run in BigQuery once data is flowing.

#### Voltage Anomaly Detection (voltage_anomaly.sql)

Objective: Identify meters where the voltage stays below **220 V** for **more than five consecutive seconds**. This non‑intrusive monitoring can alert operators to equipment issues.

Pseudo‑SQL:

WITH flagged AS (  
SELECT meter_id, event_timestamp,  
voltage_v,  
CASE WHEN voltage_v < 220 THEN 1 ELSE 0 END AS is_low,  
ROW_NUMBER() OVER (PARTITION BY meter_id ORDER BY event_timestamp) AS rn  
FROM \`smart_grid_analytics.raw_meter_readings\`  
),  
groups AS (  
SELECT meter_id,  
SUM(is_low) OVER (PARTITION BY meter_id ORDER BY rn  
ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS low_count,  
event_timestamp  
FROM flagged  
)  
SELECT meter_id, event_timestamp  
FROM groups  
WHERE low_count = 5;

The query counts the number of consecutive low‑voltage readings using a window of five rows (five seconds). It flags the timestamp where the fifth consecutive low voltage occurs.

#### Demand Response Baseline (dr_baseline.sql)

Objective: Compute **5‑minute** average loads per pole to prepare a baseline for DR programs. DR performance is typically measured as the difference between actual usage and a baseline built from **five‑minute** interval data[\[16\]](https://docs.nrel.gov/docs/fy18osti/71431.pdf).

Pseudo‑SQL:

SELECT  
pole_id,  
TIMESTAMP_TRUNC(event_timestamp, MINUTE, 5) AS interval_start,  
AVG(power_kw) AS avg_kw  
FROM \`smart_grid_analytics.raw_meter_readings\`  
GROUP BY pole_id, interval_start  
ORDER BY interval_start;

This aggregates the one‑second records into 5‑minute buckets. Additional logic could remove extreme values or adjust baselines based on regulatory rules.

### 5\. README Documentation

The README.md should guide users through:

- **Prerequisites**: gcloud CLI installed, active GCP project, Terraform installed.
- **Authentication**: Run gcloud auth login and set the project with gcloud config set project &lt;PROJECT_ID&gt;.
- **Terraform Deployment**: Initialise (terraform init), apply (terraform apply) to create resources. Capture outputs (topic, subscription, dataset, table).
- **Running the Simulator**: SSH into the VM or run locally, install dependencies (pip install -r requirements.txt), set environment variables for topic name and credentials, then start simulator.py and gateway_relay.py. The script will continuously publish messages.
- **Launching the Dataflow Job**: Use the python -m cloud_processing.streaming_pipeline entry point with parameters for project, region, input subscription and BigQuery table. Example command with Dataflow runner and machine type:

python -m cloud_processing.streaming_pipeline \\  
\--runner DataflowRunner \\  
\--project=\$PROJECT_ID \\  
\--region=us-central1 \\  
\--input_subscription=projects/\$PROJECT_ID/subscriptions/ami-meter-data-sub \\  
\--output_table=\$PROJECT_ID:smart_grid_analytics.raw_meter_readings \\  
\--worker_machine_type=n1-standard-2 \\  
\--service_account_email=dataflow-sa@\$PROJECT_ID.iam.gserviceaccount.com

- **Analysing Data**: Open BigQuery console, query the raw_meter_readings table to verify ingestion, then run the SQL scripts in the analytics directory to detect voltage anomalies and compute DR baselines.
- **Cleanup**: Provide commands to cancel the Dataflow job (gcloud dataflow jobs cancel), delete the Compute Engine VM, and run terraform destroy to delete Pub/Sub and BigQuery resources. Emphasise that BigQuery is pay‑as‑you‑use and time‑partitioned tables help control costs[\[17\]](https://medium.com/codex/a-dataflow-journey-from-pubsub-to-bigquery-68eb3270c93#:~:text=side%20note%3A%20BigQuery%20is%20a,PARTITIONTIME).

### 6\. Realism Considerations

- **High‑Frequency Data Handling**: 1‑Hz sampling is essential to illustrate AMI 2.0 capabilities. AMI 2.0 devices can produce tens of thousands of samples per second and 50 million times more data than 15‑minute meters[\[1\]](https://sense.com/wp-content/uploads/2024/05/AMI-2.0-Buyers-Guide.pdf#:~:text=Today%20we%20have%20AMI%202,vegetation%20hitting%20power%20lines%2C%20etc); partitioning and streaming infrastructure ensures the cloud can ingest this scale.
- **Network Simulation**: Use small random delays in the relay script to mimic 5G or satellite latency[\[9\]](https://www.emnify.com/blog/how-smart-meters-communicate#:~:text=Cellular%20). If desired, parameterise latency for different backhaul types.
- **Protocol Choice**: MQTT is recommended for IoT due to its lightweight publish/subscribe model[\[11\]](https://www.emnify.com/blog/how-smart-meters-communicate#:~:text=Smart%20meters%20that%20use%20cellular,transport%20data%20to%20the%20cloud). The demonstration uses the Pub/Sub Python client directly (HTTP/gRPC) but could be extended with an MQTT bridge.
- **Scalability and Reliability**: Cloud Pub/Sub provides global availability and durable messaging[\[5\]\[6\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=%2A%20), and can scale to millions of messages per second[\[7\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=%2A%20), ensuring that the pipeline remains reliable under high ingestion rates.
- **Demand Response Alignment**: The baseline computation uses 5‑minute intervals, aligning with industry practices described by NREL where DR performance is measured against a baseline built from 5‑minute meter data[\[16\]](https://docs.nrel.gov/docs/fy18osti/71431.pdf).

## Conclusion

This plan provides a detailed blueprint for building a realistic end‑to‑end pipeline for next‑generation smart meter analytics on Google Cloud. By combining simulated AMI 2.0 data, Pub/Sub's decoupled messaging, Dataflow's streaming processing and BigQuery's partitioned storage, the demonstration showcases how utilities can handle high‑frequency grid data, detect anomalies and support demand response programs. The coding agent should follow the directory structure and instructions precisely to implement the tutorial.

[\[1\]](https://sense.com/wp-content/uploads/2024/05/AMI-2.0-Buyers-Guide.pdf#:~:text=Today%20we%20have%20AMI%202,vegetation%20hitting%20power%20lines%2C%20etc) AMI-2.0-Buyers-Guide.pdf

<https://sense.com/wp-content/uploads/2024/05/AMI-2.0-Buyers-Guide.pdf>

[\[2\]](https://www.emqx.com/en/blog/why-emqx-is-your-best-google-cloud-iot-core-alternative#:~:text=Future%20of%20Google%20Cloud%20for,Shutdown%20of%20Google%20IoT%20Core) Google Cloud IoT Core is Shutting Down: How to Migrate | EMQ

<https://www.emqx.com/en/blog/why-emqx-is-your-best-google-cloud-iot-core-alternative>

[\[3\]](https://blog.balena.io/gcp-iot-core-retirement-migration-to-balena/#:~:text=The%20announcement%20for%20the%20end,discontinued%20on%20August%2016th%2C%202023) GCP IoT Core Retirement: Impact on Your IoT Stack

<https://blog.balena.io/gcp-iot-core-retirement-migration-to-balena/>

[\[4\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=Google%20Cloud%20Pub%2FSub%20is%20a,cases%20for%20your%20%2067) [\[5\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=%2A%20) [\[6\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=%2A%20) [\[7\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=%2A%20) [\[8\]](https://www.projectpro.io/article/google-cloud-pub-sub/779#:~:text=%2A%20%23%23%23%20Event) Google Cloud Pub/Sub: Messaging on The Cloud

<https://www.projectpro.io/article/google-cloud-pub-sub/779>

[\[9\]](https://www.emnify.com/blog/how-smart-meters-communicate#:~:text=Cellular%20) [\[10\]](https://www.emnify.com/blog/how-smart-meters-communicate#:~:text=While%20smart%20meters%20didn%E2%80%99t%20require,more%20frequently%20from%20more%20places) [\[11\]](https://www.emnify.com/blog/how-smart-meters-communicate#:~:text=Smart%20meters%20that%20use%20cellular,transport%20data%20to%20the%20cloud) How do smart meters communicate? | emnify Blog

<https://www.emnify.com/blog/how-smart-meters-communicate>

[\[12\]](https://medium.com/codex/a-dataflow-journey-from-pubsub-to-bigquery-68eb3270c93#:~:text=The%20Pipeline%20object%20is%20formed,PCollections%20and%20outputs%20some%20more) [\[13\]](https://medium.com/codex/a-dataflow-journey-from-pubsub-to-bigquery-68eb3270c93#:~:text=You%E2%80%99ll%20notice%20how%20we%20simply,%E2%80%9D) [\[17\]](https://medium.com/codex/a-dataflow-journey-from-pubsub-to-bigquery-68eb3270c93#:~:text=side%20note%3A%20BigQuery%20is%20a,PARTITIONTIME) A Dataflow Journey: from PubSub to BigQuery | by Nicolò Gasparini | CodeX | Medium

<https://medium.com/codex/a-dataflow-journey-from-pubsub-to-bigquery-68eb3270c93>

[\[14\]](https://moldstud.com/articles/p-effective-partitioning-strategies-for-real-time-data-processing-in-bigquery#:~:text=Analyzing%20data%20that%20arrives%20every,bytes%2C%20directly%20lowering%20operational%20expenses) [\[15\]](https://moldstud.com/articles/p-effective-partitioning-strategies-for-real-time-data-processing-in-bigquery#:~:text=Analyzing%20data%20that%20arrives%20every,bytes%2C%20directly%20lowering%20operational%20expenses) Partitioning Strategies for Real-Time Data in BigQuery | MoldStud

<https://moldstud.com/articles/p-effective-partitioning-strategies-for-real-time-data-processing-in-bigquery>

[\[16\]](https://docs.nrel.gov/docs/fy18osti/71431.pdf) Demand Response Compensation Methodologies: Case Studies for Mexico

<https://docs.nrel.gov/docs/fy18osti/71431.pdf>