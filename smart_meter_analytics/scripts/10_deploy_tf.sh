#!/bin/bash
# ============================================================================
# Terraform Deployment Script
# ============================================================================
# Deploys the GCP infrastructure for the AMI 2.0 tutorial.
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$SCRIPT_DIR/../infrastructure"

echo "============================================"
echo "AMI 2.0 Tutorial - Infrastructure Deployment"
echo "============================================"
echo ""

# Check for project ID
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" == "(unset)" ]; then
    echo "Error: No GCP project configured."
    echo "Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo "Project ID: $PROJECT_ID"
echo "Region: ${REGION:-us-central1}"
echo ""

# Navigate to infrastructure directory
cd "$INFRA_DIR"

# Initialize Terraform
echo "Initializing Terraform..."
terraform init

# Create terraform.tfvars if it doesn't exist
if [ ! -f terraform.tfvars ]; then
    echo "Creating terraform.tfvars..."
    cat > terraform.tfvars << EOF
project_id = "$PROJECT_ID"
region     = "${REGION:-us-central1}"

# Optional: Enable service account key creation for local testing
# create_sa_keys = true
EOF
    echo "Created terraform.tfvars with project_id=$PROJECT_ID"
fi

# Plan
echo ""
echo "Planning infrastructure changes..."
terraform plan -out=tfplan

# Confirm deployment
echo ""
read -p "Do you want to apply these changes? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Deployment cancelled."
    exit 0
fi

# Apply
echo ""
echo "Applying infrastructure changes..."
terraform apply tfplan

# Show outputs
echo ""
echo "============================================"
echo "Deployment Complete!"
echo "============================================"
echo ""
echo "Terraform Outputs:"
terraform output

# Save outputs to file for other scripts
terraform output -json > outputs.json
echo ""
echo "Outputs saved to $INFRA_DIR/outputs.json"

echo ""
echo "Next steps:"
echo "1. Run the edge simulator: ./20_run_edge_vm.sh"
echo "2. Launch Dataflow: ./30_launch_dataflow.sh"
echo "3. Verify data: ./40_run_queries.sh"
