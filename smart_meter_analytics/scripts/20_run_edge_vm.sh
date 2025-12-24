#!/bin/bash
# ============================================================================
# Edge Simulator Script
# ============================================================================
# Runs the edge simulation locally or sets up a VM for simulation.
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
EDGE_DIR="$ROOT_DIR/edge_simulation"

echo "============================================"
echo "AMI 2.0 Tutorial - Edge Simulator"
echo "============================================"
echo ""

# Get project and topic from Terraform outputs or environment
PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}
PUBSUB_TOPIC=${PUBSUB_TOPIC:-ami-meter-data}

if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" == "(unset)" ]; then
    echo "Error: No GCP project configured."
    echo "Set GOOGLE_CLOUD_PROJECT or run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo "Project: $PROJECT_ID"
echo "Topic: $PUBSUB_TOPIC"
echo ""

# Parse command line arguments
MODE="local"
DURATION=0
DRY_RUN=""
NETWORK_PROFILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --vm)
            MODE="vm"
            shift
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --network)
            NETWORK_PROFILE="--network-profile $2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --vm            Run on a GCE VM instead of locally"
            echo "  --duration N    Run for N seconds (0 = infinite)"
            echo "  --dry-run       Generate data without publishing to Pub/Sub"
            echo "  --network TYPE  Network profile: wired, 5g, lte_m, satellite"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ "$MODE" == "local" ]; then
    echo "Running edge simulation locally..."
    echo ""
    
    # Install dependencies
    echo "Installing Python dependencies..."
    cd "$EDGE_DIR"
    pip3 install -q -r requirements.txt
    
    # Set environment variables
    export GOOGLE_CLOUD_PROJECT="$PROJECT_ID"
    export PUBSUB_TOPIC="$PUBSUB_TOPIC"
    
    # Run the gateway relay (which includes the simulator)
    echo ""
    echo "Starting edge simulation..."
    echo "Press Ctrl+C to stop"
    echo ""
    
    python3 gateway_relay.py \
        --config config.yaml \
        --project "$PROJECT_ID" \
        --topic "$PUBSUB_TOPIC" \
        --duration "$DURATION" \
        $DRY_RUN \
        $NETWORK_PROFILE \
        --log-level INFO
        
elif [ "$MODE" == "vm" ]; then
    echo "Setting up GCE VM for edge simulation..."
    echo ""
    
    VM_NAME="ami-edge-simulator"
    ZONE="${ZONE:-us-central1-a}"
    MACHINE_TYPE="e2-small"
    
    # Check if VM exists
    if gcloud compute instances describe "$VM_NAME" --zone="$ZONE" &> /dev/null; then
        echo "VM $VM_NAME already exists. Connecting..."
    else
        echo "Creating VM $VM_NAME..."
        
        gcloud compute instances create "$VM_NAME" \
            --zone="$ZONE" \
            --machine-type="$MACHINE_TYPE" \
            --image-family=debian-11 \
            --image-project=debian-cloud \
            --scopes=cloud-platform \
            --metadata=startup-script='#!/bin/bash
apt-get update
apt-get install -y python3-pip git
pip3 install google-cloud-pubsub pyyaml numpy python-dateutil
'
        
        echo "Waiting for VM to be ready..."
        sleep 30
    fi
    
    # Copy edge simulation files to VM
    echo "Copying simulation files to VM..."
    gcloud compute scp --recurse --zone="$ZONE" \
        "$EDGE_DIR" "$VM_NAME:~/"
    
    # Run simulation on VM
    echo ""
    echo "Starting simulation on VM..."
    echo "Press Ctrl+C to stop"
    echo ""
    
    gcloud compute ssh "$VM_NAME" --zone="$ZONE" -- \
        "cd ~/edge_simulation && \
         export GOOGLE_CLOUD_PROJECT=$PROJECT_ID && \
         export PUBSUB_TOPIC=$PUBSUB_TOPIC && \
         python3 gateway_relay.py --config config.yaml --duration $DURATION"
fi
