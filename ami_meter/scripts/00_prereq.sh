#!/bin/bash
# ============================================================================
# Prerequisites Check Script
# ============================================================================
# Verifies that all required tools and configurations are in place
# for the AMI 2.0 Smart Meter Analytics tutorial.
# ============================================================================

set -e

echo "============================================"
echo "AMI 2.0 Tutorial - Prerequisites Check"
echo "============================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0

# Function to check if command exists
check_command() {
    local cmd=$1
    local install_hint=$2
    
    if command -v "$cmd" &> /dev/null; then
        echo -e "${GREEN}✓${NC} $cmd is installed: $(command -v $cmd)"
        return 0
    else
        echo -e "${RED}✗${NC} $cmd is NOT installed"
        echo "  Install: $install_hint"
        ERRORS=$((ERRORS + 1))
        return 1
    fi
}

# Function to check minimum version
check_version() {
    local cmd=$1
    local min_version=$2
    local current_version=$3
    
    if [ "$(printf '%s\n' "$min_version" "$current_version" | sort -V | head -n1)" = "$min_version" ]; then 
        echo -e "  ${GREEN}✓${NC} Version $current_version >= $min_version"
        return 0
    else
        echo -e "  ${YELLOW}!${NC} Version $current_version < $min_version (upgrade recommended)"
        return 1
    fi
}

echo "1. Checking required CLI tools..."
echo "-----------------------------------"

# Check gcloud
check_command "gcloud" "https://cloud.google.com/sdk/docs/install"
if command -v gcloud &> /dev/null; then
    GCLOUD_VERSION=$(gcloud version 2>/dev/null | head -1 | awk '{print $4}')
    echo "  Version: $GCLOUD_VERSION"
fi

# Check Terraform
check_command "terraform" "https://developer.hashicorp.com/terraform/install"
if command -v terraform &> /dev/null; then
    TF_VERSION=$(terraform version -json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['terraform_version'])" 2>/dev/null || terraform version | head -1 | awk '{print $2}' | tr -d 'v')
    check_version "terraform" "1.0.0" "$TF_VERSION"
fi

# Check Python
check_command "python3" "https://www.python.org/downloads/"
if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    check_version "python3" "3.9.0" "$PY_VERSION"
fi

# Check pip
check_command "pip3" "Usually installed with Python"

echo ""
echo "2. Checking GCP authentication..."
echo "-----------------------------------"

# Check if authenticated
if gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1 | grep -q "@"; then
    ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1)
    echo -e "${GREEN}✓${NC} Authenticated as: $ACCOUNT"
else
    echo -e "${RED}✗${NC} Not authenticated with gcloud"
    echo "  Run: gcloud auth login"
    ERRORS=$((ERRORS + 1))
fi

# Check application default credentials
if gcloud auth application-default print-access-token &> /dev/null; then
    echo -e "${GREEN}✓${NC} Application Default Credentials configured"
else
    echo -e "${YELLOW}!${NC} Application Default Credentials not set"
    echo "  Run: gcloud auth application-default login"
fi

echo ""
echo "3. Checking GCP project configuration..."
echo "-----------------------------------"

# Check if project is set
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -n "$PROJECT_ID" ] && [ "$PROJECT_ID" != "(unset)" ]; then
    echo -e "${GREEN}✓${NC} Project configured: $PROJECT_ID"
    
    # Check if project exists and is accessible
    if gcloud projects describe "$PROJECT_ID" &> /dev/null; then
        echo -e "${GREEN}✓${NC} Project is accessible"
    else
        echo -e "${RED}✗${NC} Cannot access project $PROJECT_ID"
        echo "  Check permissions or project ID"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${RED}✗${NC} No project configured"
    echo "  Run: gcloud config set project YOUR_PROJECT_ID"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "4. Checking required APIs..."
echo "-----------------------------------"

REQUIRED_APIS=(
    "pubsub.googleapis.com"
    "dataflow.googleapis.com"
    "bigquery.googleapis.com"
    "storage.googleapis.com"
    "compute.googleapis.com"
    "run.googleapis.com"
)

if [ -n "$PROJECT_ID" ] && [ "$PROJECT_ID" != "(unset)" ]; then
    for api in "${REQUIRED_APIS[@]}"; do
        if gcloud services list --enabled --filter="name:$api" --format="value(name)" 2>/dev/null | grep -q "$api"; then
            echo -e "${GREEN}✓${NC} $api is enabled"
        else
            echo -e "${YELLOW}!${NC} $api is NOT enabled"
            echo "  Enable: gcloud services enable $api"
        fi
    done
else
    echo "  Skipped - no project configured"
fi

echo ""
echo "5. Checking Python packages..."
echo "-----------------------------------"

REQUIRED_PACKAGES=(
    "google-cloud-pubsub"
    "google-cloud-bigquery"
    "apache-beam"
    "numpy"
    "pyyaml"
)

for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if pip3 show "$pkg" &> /dev/null; then
        VERSION=$(pip3 show "$pkg" 2>/dev/null | grep "Version:" | awk '{print $2}')
        echo -e "${GREEN}✓${NC} $pkg ($VERSION)"
    else
        echo -e "${YELLOW}!${NC} $pkg is not installed"
        echo "  Install: pip3 install $pkg"
    fi
done

echo ""
echo "============================================"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}All prerequisites are met!${NC}"
    echo "You can proceed with the tutorial."
else
    echo -e "${RED}Found $ERRORS error(s) that need to be fixed.${NC}"
    echo "Please resolve the issues above before continuing."
fi
echo "============================================"

exit $ERRORS
