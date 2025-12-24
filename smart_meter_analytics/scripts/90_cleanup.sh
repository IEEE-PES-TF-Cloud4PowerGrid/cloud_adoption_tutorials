#!/bin/bash
# ============================================================================
# Cleanup Script
# ============================================================================
# Removes all resources created by the AMI 2.0 tutorial.
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
INFRA_DIR="$ROOT_DIR/infrastructure"

echo "============================================"
echo "AMI 2.0 Tutorial - Cleanup"
echo "============================================"
echo ""

PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}
REGION=${REGION:-us-central1}

echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

echo "This script will delete:"
echo "  - All Dataflow jobs"
echo "  - Pub/Sub topics and subscriptions"
echo "  - BigQuery dataset and tables"
echo "  - Cloud Storage buckets"
echo "  - Service accounts"
echo "  - GCE VM (if created)"
echo "  - Cloud Run service (if deployed)"
echo ""

read -p "Are you sure you want to proceed? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo "Starting cleanup..."
echo ""

# Step 1: Cancel Dataflow jobs
echo "1. Cancelling Dataflow jobs..."
JOBS=$(gcloud dataflow jobs list --region="$REGION" --status=active --format="value(id)" 2>/dev/null || true)
if [ -n "$JOBS" ]; then
    for job_id in $JOBS; do
        echo "   Cancelling job: $job_id"
        gcloud dataflow jobs cancel "$job_id" --region="$REGION" 2>/dev/null || true
    done
    echo "   Waiting for jobs to cancel..."
    sleep 30
else
    echo "   No active jobs found."
fi

# Step 2: Delete Cloud Run service
echo ""
echo "2. Deleting Cloud Run service..."
gcloud run services delete ami-analytics-api --region="$REGION" --quiet 2>/dev/null || echo "   No Cloud Run service found."

# Step 3: Delete GCE VM
echo ""
echo "3. Deleting GCE VM..."
gcloud compute instances delete ami-edge-simulator --zone="${ZONE:-us-central1-a}" --quiet 2>/dev/null || echo "   No VM found."

# Step 4: Terraform destroy
echo ""
echo "4. Running Terraform destroy..."
cd "$INFRA_DIR"
if [ -f "terraform.tfstate" ]; then
    terraform destroy -auto-approve
else
    echo "   No Terraform state found."
fi

# Step 5: Clean up local files
echo ""
echo "5. Cleaning up local files..."
rm -f "$INFRA_DIR/tfplan"
rm -f "$INFRA_DIR/outputs.json"
rm -rf "$INFRA_DIR/.terraform"
rm -f "$INFRA_DIR/.terraform.lock.hcl"
rm -f "$INFRA_DIR/terraform.tfstate*"

echo ""
echo "============================================"
echo "Cleanup Complete!"
echo "============================================"
echo ""
echo "All tutorial resources have been deleted."
echo ""
echo "Note: Some resources may take a few minutes to fully delete."
echo "Check the GCP Console to verify all resources are removed."
