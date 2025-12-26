#!/bin/bash
# ============================================================================
# Cloud Monitoring Dashboard Setup Script
# ============================================================================
# Creates the real-time monitoring dashboard for the AMI 2.0 tutorial.
# The dashboard is also created by Terraform, but this script can be used
# for standalone dashboard creation or updates.
# ============================================================================

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}AMI 2.0 Cloud Monitoring Dashboard Setup${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Check for required tools
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI is not installed${NC}"
    exit 1
fi

# Get project ID
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: No project ID found. Set GOOGLE_CLOUD_PROJECT or run 'gcloud config set project PROJECT_ID'${NC}"
    exit 1
fi

echo -e "Using project: ${GREEN}${PROJECT_ID}${NC}"
echo ""

# Enable required APIs
echo -e "${YELLOW}Enabling required APIs...${NC}"
gcloud services enable monitoring.googleapis.com --project="$PROJECT_ID" 2>/dev/null || true

# Create custom metric descriptors
echo -e "${YELLOW}Creating custom metric descriptors...${NC}"

# Function to create a metric descriptor
create_metric_descriptor() {
    local metric_type=$1
    local display_name=$2
    local description=$3
    local unit=$4
    local value_type=${5:-DOUBLE}
    
    # Check if metric already exists
    if gcloud monitoring metrics-descriptors describe "custom.googleapis.com/ami/${metric_type}" --project="$PROJECT_ID" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Metric '${metric_type}' already exists"
        return 0
    fi
    
    # Create the metric descriptor
    cat > /tmp/metric_descriptor.json << EOF
{
  "type": "custom.googleapis.com/ami/${metric_type}",
  "metricKind": "GAUGE",
  "valueType": "${value_type}",
  "unit": "${unit}",
  "description": "${description}",
  "displayName": "${display_name}",
  "labels": [
    {
      "key": "pole_id",
      "valueType": "STRING",
      "description": "Pole/gateway identifier"
    }
  ]
}
EOF

    if gcloud monitoring metrics-descriptors create --project="$PROJECT_ID" --descriptor-file=/tmp/metric_descriptor.json &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Created metric '${metric_type}'"
    else
        echo -e "  ${YELLOW}!${NC} Could not create metric '${metric_type}' (may already exist)"
    fi
}

# Create all metrics
create_metric_descriptor "voltage_avg" "Average Voltage" "Average RMS voltage across meters at a pole" "V"
create_metric_descriptor "voltage_min" "Minimum Voltage" "Minimum RMS voltage at a pole" "V"
create_metric_descriptor "voltage_max" "Maximum Voltage" "Maximum RMS voltage at a pole" "V"
create_metric_descriptor "power_total_kw" "Total Power" "Total active power consumption at a pole" "kW"
create_metric_descriptor "voltage_sag_count" "Voltage Sag Count" "Number of voltage sag events detected" "1" "INT64"
create_metric_descriptor "health_score" "Health Score" "Overall health score based on voltage quality" "%" 
create_metric_descriptor "active_meter_count" "Active Meter Count" "Number of active meters at a pole" "1" "INT64"

echo ""
echo -e "${YELLOW}Creating monitoring dashboard...${NC}"

# Create the dashboard JSON
cat > /tmp/dashboard.json << 'DASHBOARD_EOF'
{
  "displayName": "AMI 2.0 Smart Meter Real-Time Dashboard",
  "mosaicLayout": {
    "columns": 12,
    "tiles": [
      {
        "width": 4,
        "height": 4,
        "widget": {
          "title": "Total Messages (Pub/Sub rate)",
          "scorecard": {
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_delivered_messages\"",
                "aggregation": {
                  "alignmentPeriod": "60s",
                  "perSeriesAligner": "ALIGN_RATE",
                  "crossSeriesReducer": "REDUCE_SUM"
                }
              }
            },
            "sparkChartView": {
              "sparkChartType": "SPARK_LINE"
            }
          }
        }
      },
      {
        "xPos": 4,
        "width": 4,
        "height": 4,
        "widget": {
          "title": "Pub/Sub Backlog",
          "scorecard": {
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\"",
                "aggregation": {
                  "alignmentPeriod": "60s",
                  "perSeriesAligner": "ALIGN_MEAN"
                }
              }
            },
            "thresholds": [
              {"color": "YELLOW", "direction": "ABOVE", "value": 100},
              {"color": "RED", "direction": "ABOVE", "value": 1000}
            ]
          }
        }
      },
      {
        "xPos": 8,
        "width": 4,
        "height": 4,
        "widget": {
          "title": "Dataflow System Lag (s)",
          "scorecard": {
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "resource.type=\"dataflow_job\" AND metric.type=\"dataflow.googleapis.com/job/system_lag\"",
                "aggregation": {
                  "alignmentPeriod": "60s",
                  "perSeriesAligner": "ALIGN_MAX"
                }
              }
            },
            "thresholds": [
              {"color": "YELLOW", "direction": "ABOVE", "value": 30},
              {"color": "RED", "direction": "ABOVE", "value": 120}
            ]
          }
        }
      },
      {
        "yPos": 4,
        "width": 6,
        "height": 4,
        "widget": {
          "title": "Average Voltage by Pole (V)",
          "xyChart": {
            "dataSets": [
              {
                "timeSeriesQuery": {
                  "timeSeriesFilter": {
                    "filter": "metric.type=\"custom.googleapis.com/ami/voltage_avg\"",
                    "aggregation": {
                      "alignmentPeriod": "60s",
                      "perSeriesAligner": "ALIGN_MEAN"
                    }
                  }
                },
                "plotType": "LINE"
              }
            ],
            "yAxis": {"label": "Voltage (V)", "scale": "LINEAR"},
            "thresholds": [
              {"label": "Sag Threshold", "value": 220, "color": "YELLOW"},
              {"label": "Nominal", "value": 240, "color": "BLUE"}
            ]
          }
        }
      },
      {
        "yPos": 4,
        "xPos": 6,
        "width": 6,
        "height": 4,
        "widget": {
          "title": "Total Power Consumption (kW)",
          "xyChart": {
            "dataSets": [
              {
                "timeSeriesQuery": {
                  "timeSeriesFilter": {
                    "filter": "metric.type=\"custom.googleapis.com/ami/power_total_kw\"",
                    "aggregation": {
                      "alignmentPeriod": "60s",
                      "perSeriesAligner": "ALIGN_MEAN"
                    }
                  }
                },
                "plotType": "STACKED_AREA"
              }
            ],
            "yAxis": {"label": "Power (kW)", "scale": "LINEAR"}
          }
        }
      },
      {
        "yPos": 8,
        "width": 4,
        "height": 4,
        "widget": {
          "title": "Voltage Sag Events (5 min)",
          "scorecard": {
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "metric.type=\"custom.googleapis.com/ami/voltage_sag_count\"",
                "aggregation": {
                  "alignmentPeriod": "300s",
                  "perSeriesAligner": "ALIGN_SUM",
                  "crossSeriesReducer": "REDUCE_SUM"
                }
              }
            },
            "thresholds": [
              {"color": "YELLOW", "direction": "ABOVE", "value": 5},
              {"color": "RED", "direction": "ABOVE", "value": 20}
            ]
          }
        }
      },
      {
        "yPos": 8,
        "xPos": 4,
        "width": 4,
        "height": 4,
        "widget": {
          "title": "Meter Health Score (%)",
          "scorecard": {
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "metric.type=\"custom.googleapis.com/ami/health_score\"",
                "aggregation": {
                  "alignmentPeriod": "60s",
                  "perSeriesAligner": "ALIGN_MEAN",
                  "crossSeriesReducer": "REDUCE_MEAN"
                }
              }
            },
            "thresholds": [
              {"color": "RED", "direction": "BELOW", "value": 80},
              {"color": "YELLOW", "direction": "BELOW", "value": 95}
            ]
          }
        }
      },
      {
        "yPos": 8,
        "xPos": 8,
        "width": 4,
        "height": 4,
        "widget": {
          "title": "Active Meters",
          "scorecard": {
            "timeSeriesQuery": {
              "timeSeriesFilter": {
                "filter": "metric.type=\"custom.googleapis.com/ami/active_meter_count\"",
                "aggregation": {
                  "alignmentPeriod": "60s",
                  "perSeriesAligner": "ALIGN_MEAN",
                  "crossSeriesReducer": "REDUCE_SUM"
                }
              }
            }
          }
        }
      },
      {
        "yPos": 12,
        "width": 6,
        "height": 5,
        "widget": {
          "title": "Voltage Distribution (Min/Avg/Max)",
          "xyChart": {
            "dataSets": [
              {
                "timeSeriesQuery": {
                  "timeSeriesFilter": {
                    "filter": "metric.type=\"custom.googleapis.com/ami/voltage_min\"",
                    "aggregation": {"alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_MIN"}
                  }
                },
                "legendTemplate": "Min Voltage",
                "plotType": "LINE"
              },
              {
                "timeSeriesQuery": {
                  "timeSeriesFilter": {
                    "filter": "metric.type=\"custom.googleapis.com/ami/voltage_avg\"",
                    "aggregation": {"alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_MEAN"}
                  }
                },
                "legendTemplate": "Avg Voltage",
                "plotType": "LINE"
              },
              {
                "timeSeriesQuery": {
                  "timeSeriesFilter": {
                    "filter": "metric.type=\"custom.googleapis.com/ami/voltage_max\"",
                    "aggregation": {"alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_MAX"}
                  }
                },
                "legendTemplate": "Max Voltage",
                "plotType": "LINE"
              }
            ],
            "yAxis": {"label": "Voltage (V)", "scale": "LINEAR"}
          }
        }
      },
      {
        "yPos": 12,
        "xPos": 6,
        "width": 6,
        "height": 5,
        "widget": {
          "title": "BigQuery Streaming Inserts",
          "xyChart": {
            "dataSets": [
              {
                "timeSeriesQuery": {
                  "timeSeriesFilter": {
                    "filter": "resource.type=\"bigquery_dataset\" AND metric.type=\"bigquery.googleapis.com/storage/streaming_insert_count\"",
                    "aggregation": {
                      "alignmentPeriod": "60s",
                      "perSeriesAligner": "ALIGN_RATE",
                      "crossSeriesReducer": "REDUCE_SUM"
                    }
                  }
                },
                "plotType": "LINE"
              }
            ],
            "yAxis": {"label": "Inserts/sec", "scale": "LINEAR"}
          }
        }
      }
    ]
  }
}
DASHBOARD_EOF

# Check if dashboard already exists
DASHBOARD_NAME="AMI 2.0 Smart Meter Real-Time Dashboard"
EXISTING_DASHBOARD=$(gcloud monitoring dashboards list --project="$PROJECT_ID" --format="value(name)" --filter="displayName='${DASHBOARD_NAME}'" 2>/dev/null | head -1)

if [ -n "$EXISTING_DASHBOARD" ]; then
    echo -e "  ${YELLOW}Dashboard already exists. Updating...${NC}"
    gcloud monitoring dashboards update "$EXISTING_DASHBOARD" --project="$PROJECT_ID" --config-from-file=/tmp/dashboard.json
    echo -e "  ${GREEN}✓${NC} Dashboard updated"
else
    gcloud monitoring dashboards create --project="$PROJECT_ID" --config-from-file=/tmp/dashboard.json
    echo -e "  ${GREEN}✓${NC} Dashboard created"
fi

# Cleanup
rm -f /tmp/metric_descriptor.json /tmp/dashboard.json

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}Dashboard setup complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "View the dashboard at:"
echo -e "${BLUE}https://console.cloud.google.com/monitoring/dashboards?project=${PROJECT_ID}${NC}"
echo ""
echo -e "Look for: '${DASHBOARD_NAME}'"
echo ""
