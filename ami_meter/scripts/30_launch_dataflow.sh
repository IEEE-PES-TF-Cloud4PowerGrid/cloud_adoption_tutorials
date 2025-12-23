#!/bin/bash
# ============================================================================
# Dataflow Pipeline Launch Script
# ============================================================================
# Launches the streaming Dataflow pipeline for AMI data processing.
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
CLOUD_DIR="$ROOT_DIR/cloud_processing"
INFRA_DIR="$ROOT_DIR/infrastructure"

echo "============================================"
echo "AMI 2.0 Tutorial - Dataflow Pipeline"
echo "============================================"
echo ""

# Get configuration
PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}
REGION=${REGION:-us-central1}

if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" == "(unset)" ]; then
    echo "Error: No GCP project configured."
    exit 1
fi

# Load outputs from Terraform if available
if [ -f "$INFRA_DIR/outputs.json" ]; then
    echo "Loading configuration from Terraform outputs..."
    SUBSCRIPTION=$(cat "$INFRA_DIR/outputs.json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('pubsub_subscription_id',{}).get('value',''))" 2>/dev/null || echo "")
    BQ_TABLE=$(cat "$INFRA_DIR/outputs.json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bq_raw_table_full_id',{}).get('value',''))" 2>/dev/null || echo "")
    RAW_BUCKET=$(cat "$INFRA_DIR/outputs.json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('raw_archive_bucket',{}).get('value',''))" 2>/dev/null || echo "")
    ARTIFACTS_BUCKET=$(cat "$INFRA_DIR/outputs.json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dataflow_artifacts_bucket',{}).get('value',''))" 2>/dev/null || echo "")
    DATAFLOW_SA=$(cat "$INFRA_DIR/outputs.json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dataflow_sa_email',{}).get('value',''))" 2>/dev/null || echo "")
fi

# Default values if not from Terraform
SUBSCRIPTION=${SUBSCRIPTION:-"projects/$PROJECT_ID/subscriptions/ami-meter-data-sub"}
BQ_TABLE=${BQ_TABLE:-"$PROJECT_ID:smart_grid_analytics.raw_meter_readings"}
RAW_BUCKET=${RAW_BUCKET:-"$PROJECT_ID-ami-raw-archive"}
ARTIFACTS_BUCKET=${ARTIFACTS_BUCKET:-"$PROJECT_ID-ami-dataflow-artifacts"}
DATAFLOW_SA=${DATAFLOW_SA:-"dataflow-sa@$PROJECT_ID.iam.gserviceaccount.com"}

echo "Configuration:"
echo "  Project: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Subscription: $SUBSCRIPTION"
echo "  BQ Table: $BQ_TABLE"
echo "  Raw Archive Bucket: $RAW_BUCKET"
echo "  Artifacts Bucket: $ARTIFACTS_BUCKET"
echo "  Service Account: $DATAFLOW_SA"
echo ""

# Parse command line arguments
RUNNER="DataflowRunner"
MACHINE_TYPE="e2-standard-2"
MAX_WORKERS=2
LOCAL_MODE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --local)
            RUNNER="DirectRunner"
            LOCAL_MODE="true"
            shift
            ;;
        --machine-type)
            MACHINE_TYPE="$2"
            shift 2
            ;;
        --max-workers)
            MAX_WORKERS="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --local            Run locally with DirectRunner (for testing)"
            echo "  --machine-type     Worker machine type (default: e2-standard-2)"
            echo "  --max-workers N    Maximum number of workers (default: 2)"
            echo "  --help             Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Install dependencies
echo "Installing Python dependencies..."
cd "$CLOUD_DIR"
pip3 install -q -r requirements.txt

if [ -n "$LOCAL_MODE" ]; then
    echo ""
    echo "Running pipeline locally with DirectRunner..."
    echo "Note: Local mode is for testing only."
    echo ""
    
    python3 streaming_pipeline.py \
        --runner DirectRunner \
        --project="$PROJECT_ID" \
        --input_subscription="$SUBSCRIPTION" \
        --output_bq_table="$BQ_TABLE" \
        --raw_archive_bucket="$RAW_BUCKET"
else
    echo ""
    echo "Launching Dataflow pipeline..."
    echo ""
    
    JOB_NAME="ami-streaming-$(date +%Y%m%d-%H%M%S)"
    
    python3 streaming_pipeline.py \
        --runner DataflowRunner \
        --project="$PROJECT_ID" \
        --region="$REGION" \
        --job_name="$JOB_NAME" \
        --input_subscription="$SUBSCRIPTION" \
        --output_bq_table="$BQ_TABLE" \
        --raw_archive_bucket="$RAW_BUCKET" \
        --temp_location="gs://$ARTIFACTS_BUCKET/temp" \
        --staging_location="gs://$ARTIFACTS_BUCKET/staging" \
        --service_account_email="$DATAFLOW_SA" \
        --worker_machine_type="$MACHINE_TYPE" \
        --max_num_workers="$MAX_WORKERS" \
        --streaming \
        --save_main_session \
        --setup_file="$CLOUD_DIR/setup.py"
    
    echo ""
    echo "============================================"
    echo "Dataflow Job Submitted!"
    echo "============================================"
    echo ""
    echo "Job Name: $JOB_NAME"
    echo ""
    echo "View in Console:"
    echo "https://console.cloud.google.com/dataflow/jobs/$REGION/$JOB_NAME?project=$PROJECT_ID"
    echo ""
    echo "Monitor with:"
    echo "  gcloud dataflow jobs show $JOB_NAME --region=$REGION"
    echo ""
    echo "Cancel with:"
    echo "  gcloud dataflow jobs cancel $JOB_NAME --region=$REGION"
fi
