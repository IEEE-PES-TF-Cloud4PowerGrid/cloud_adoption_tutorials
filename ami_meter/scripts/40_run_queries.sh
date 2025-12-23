#!/bin/bash
# ============================================================================
# Query Execution Script
# ============================================================================
# Runs analytics queries against BigQuery to validate the pipeline.
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
ANALYTICS_DIR="$ROOT_DIR/analytics"

echo "============================================"
echo "AMI 2.0 Tutorial - Analytics Queries"
echo "============================================"
echo ""

PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}
DATASET="smart_grid_analytics"

if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" == "(unset)" ]; then
    echo "Error: No GCP project configured."
    exit 1
fi

echo "Project: $PROJECT_ID"
echo "Dataset: $DATASET"
echo ""

# Function to run a query
run_query() {
    local description=$1
    local query=$2
    
    echo "-------------------------------------------"
    echo "$description"
    echo "-------------------------------------------"
    bq query --use_legacy_sql=false --format=prettyjson "$query"
    echo ""
}

# Parse command line
QUERY_TYPE=${1:-all}

case $QUERY_TYPE in
    count)
        run_query "Total row count (last 24 hours)" "
            SELECT COUNT(*) as total_readings
            FROM \`$PROJECT_ID.$DATASET.raw_meter_readings\`
            WHERE event_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
        "
        ;;
        
    sample)
        run_query "Sample readings (most recent 10)" "
            SELECT 
                event_ts,
                meter_id,
                pole_id,
                voltage_v,
                current_a,
                power_kw
            FROM \`$PROJECT_ID.$DATASET.raw_meter_readings\`
            ORDER BY event_ts DESC
            LIMIT 10
        "
        ;;
        
    stats)
        run_query "Statistics by pole (last hour)" "
            SELECT
                pole_id,
                COUNT(DISTINCT meter_id) as meters,
                COUNT(*) as readings,
                ROUND(AVG(voltage_v), 2) as avg_voltage,
                ROUND(MIN(voltage_v), 2) as min_voltage,
                ROUND(MAX(voltage_v), 2) as max_voltage,
                ROUND(SUM(power_kw), 2) as total_power_kw
            FROM \`$PROJECT_ID.$DATASET.raw_meter_readings\`
            WHERE event_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
            GROUP BY pole_id
            ORDER BY pole_id
        "
        ;;
        
    anomalies)
        echo "Running voltage anomaly detection..."
        # Replace PROJECT_ID in the SQL file and run
        sed "s/PROJECT_ID/$PROJECT_ID/g" "$ANALYTICS_DIR/voltage_anomaly.sql" | \
            bq query --use_legacy_sql=false --format=prettyjson
        ;;
        
    baseline)
        echo "Computing DR baselines (this may take a moment)..."
        sed "s/PROJECT_ID/$PROJECT_ID/g" "$ANALYTICS_DIR/dr_baseline_5min.sql" | \
            bq query --use_legacy_sql=false --format=prettyjson
        ;;
        
    health)
        echo "Generating pole health summary..."
        sed "s/PROJECT_ID/$PROJECT_ID/g" "$ANALYTICS_DIR/feeder_health_summary.sql" | \
            bq query --use_legacy_sql=false --format=prettyjson
        ;;
        
    all)
        echo "Running all validation queries..."
        echo ""
        
        run_query "1. Total row count" "
            SELECT COUNT(*) as total_readings
            FROM \`$PROJECT_ID.$DATASET.raw_meter_readings\`
        "
        
        run_query "2. Readings by hour (last 24h)" "
            SELECT
                TIMESTAMP_TRUNC(event_ts, HOUR) as hour,
                COUNT(*) as readings,
                COUNT(DISTINCT meter_id) as meters
            FROM \`$PROJECT_ID.$DATASET.raw_meter_readings\`
            WHERE event_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            GROUP BY hour
            ORDER BY hour DESC
            LIMIT 24
        "
        
        run_query "3. Sample readings" "
            SELECT 
                event_ts,
                meter_id,
                pole_id,
                ROUND(voltage_v, 2) as voltage_v,
                ROUND(power_kw, 3) as power_kw
            FROM \`$PROJECT_ID.$DATASET.raw_meter_readings\`
            ORDER BY event_ts DESC
            LIMIT 5
        "
        
        run_query "4. Low voltage events" "
            SELECT 
                meter_id,
                pole_id,
                event_ts,
                ROUND(voltage_v, 2) as voltage_v
            FROM \`$PROJECT_ID.$DATASET.raw_meter_readings\`
            WHERE voltage_v < 220
            ORDER BY event_ts DESC
            LIMIT 10
        "
        ;;
        
    *)
        echo "Usage: $0 [QUERY_TYPE]"
        echo ""
        echo "Query types:"
        echo "  count      - Total reading count"
        echo "  sample     - Sample recent readings"
        echo "  stats      - Statistics by pole"
        echo "  anomalies  - Run voltage anomaly detection"
        echo "  baseline   - Compute DR baselines"
        echo "  health     - Generate health summary"
        echo "  all        - Run all validation queries (default)"
        exit 1
        ;;
esac

echo ""
echo "============================================"
echo "Queries completed!"
echo "============================================"
