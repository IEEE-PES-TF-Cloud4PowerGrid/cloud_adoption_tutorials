#!/usr/bin/env python3
"""
AMI 2.0 Analytics API

FastAPI service for on-demand smart meter analytics queries.
Deployed on Cloud Run for serverless scaling.

Endpoints:
- GET /health - Health check
- GET /pole/{pole_id}/summary - Pole summary metrics
- GET /anomalies - Recent voltage anomaly events
- POST /dr/compute - Compute DR event performance
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import bigquery
from pydantic import BaseModel, Field

# Configuration from environment
PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT', '')
DATASET_ID = os.environ.get('BQ_DATASET', 'smart_grid_analytics')

# Initialize FastAPI app
app = FastAPI(
    title="AMI 2.0 Analytics API",
    description="On-demand analytics for AMI 2.0 smart meter data",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize BigQuery client
bq_client = bigquery.Client(project=PROJECT_ID)


# ===========================================================================
# Pydantic Models
# ===========================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    project_id: str
    dataset_id: str
    timestamp: datetime


class PoleSummary(BaseModel):
    """Summary metrics for a pole."""
    pole_id: str
    start_time: datetime
    end_time: datetime
    meter_count: int
    reading_count: int
    avg_voltage_v: float
    min_voltage_v: float
    max_voltage_v: float
    voltage_stddev: float
    total_power_kw: float
    avg_power_kw: float
    peak_power_kw: float
    low_voltage_pct: float
    health_score: float


class VoltageAnomaly(BaseModel):
    """Voltage anomaly event."""
    meter_id: str
    pole_id: str
    event_start: datetime
    event_end: datetime
    duration_seconds: int
    min_voltage_v: float
    avg_voltage_v: float
    severity: str


class DRComputeRequest(BaseModel):
    """Request for DR event computation."""
    pole_ids: List[str] = Field(..., description="List of pole IDs to analyze")
    event_date: str = Field(..., description="Event date (YYYY-MM-DD)")
    event_start_hour: int = Field(..., ge=0, le=23, description="Event start hour")
    event_end_hour: int = Field(..., ge=0, le=23, description="Event end hour")


class DRPerformance(BaseModel):
    """DR event performance for a pole."""
    pole_id: str
    avg_actual_kw: float
    avg_baseline_kw: float
    avg_reduction_kw: float
    reduction_percent: float
    total_reduction_kwh: float


class DRComputeResponse(BaseModel):
    """Response for DR computation."""
    event_date: str
    event_window: str
    poles: List[DRPerformance]
    total_reduction_kwh: float


# ===========================================================================
# Helper Functions
# ===========================================================================

def get_table_ref(table_name: str) -> str:
    """Get fully qualified table reference."""
    return f"`{PROJECT_ID}.{DATASET_ID}.{table_name}`"


def run_query(query: str) -> List[dict]:
    """Execute a BigQuery query and return results as list of dicts."""
    try:
        query_job = bq_client.query(query)
        results = query_job.result()
        return [dict(row) for row in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


# ===========================================================================
# Endpoints
# ===========================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        project_id=PROJECT_ID,
        dataset_id=DATASET_ID,
        timestamp=datetime.utcnow(),
    )


@app.get("/pole/{pole_id}/summary", response_model=PoleSummary)
async def get_pole_summary(
    pole_id: str,
    start: Optional[datetime] = Query(
        None, 
        description="Start time (defaults to 1 hour ago)"
    ),
    end: Optional[datetime] = Query(
        None, 
        description="End time (defaults to now)"
    ),
):
    """
    Get summary metrics for a specific pole.
    
    Returns voltage quality, power consumption, and health metrics.
    """
    # Default time range
    if end is None:
        end = datetime.utcnow()
    if start is None:
        start = end - timedelta(hours=1)
    
    query = f"""
    SELECT
        @pole_id AS pole_id,
        @start_time AS start_time,
        @end_time AS end_time,
        COUNT(DISTINCT meter_id) AS meter_count,
        COUNT(*) AS reading_count,
        AVG(voltage_v) AS avg_voltage_v,
        MIN(voltage_v) AS min_voltage_v,
        MAX(voltage_v) AS max_voltage_v,
        STDDEV(voltage_v) AS voltage_stddev,
        SUM(power_kw) AS total_power_kw,
        AVG(power_kw) AS avg_power_kw,
        MAX(power_kw) AS peak_power_kw,
        ROUND(COUNTIF(voltage_v < 220) / COUNT(*) * 100, 2) AS low_voltage_pct,
        -- Health score calculation
        ROUND(
            (1 - COUNTIF(voltage_v < 220 OR voltage_v > 260) / COUNT(*)) * 100,
            1
        ) AS health_score
    FROM {get_table_ref('raw_meter_readings')}
    WHERE 
        pole_id = @pole_id
        AND event_ts >= @start_time
        AND event_ts <= @end_time
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("pole_id", "STRING", pole_id),
            bigquery.ScalarQueryParameter("start_time", "TIMESTAMP", start),
            bigquery.ScalarQueryParameter("end_time", "TIMESTAMP", end),
        ]
    )
    
    try:
        query_job = bq_client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        if not results or results[0]['reading_count'] == 0:
            raise HTTPException(
                status_code=404, 
                detail=f"No data found for pole {pole_id}"
            )
        
        row = results[0]
        return PoleSummary(
            pole_id=pole_id,
            start_time=start,
            end_time=end,
            meter_count=row['meter_count'],
            reading_count=row['reading_count'],
            avg_voltage_v=round(row['avg_voltage_v'], 2),
            min_voltage_v=round(row['min_voltage_v'], 2),
            max_voltage_v=round(row['max_voltage_v'], 2),
            voltage_stddev=round(row['voltage_stddev'] or 0, 2),
            total_power_kw=round(row['total_power_kw'], 2),
            avg_power_kw=round(row['avg_power_kw'], 3),
            peak_power_kw=round(row['peak_power_kw'], 3),
            low_voltage_pct=row['low_voltage_pct'],
            health_score=row['health_score'],
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@app.get("/anomalies", response_model=List[VoltageAnomaly])
async def get_anomalies(
    start: Optional[datetime] = Query(
        None,
        description="Start time (defaults to 24 hours ago)"
    ),
    end: Optional[datetime] = Query(
        None,
        description="End time (defaults to now)"
    ),
    min_duration_seconds: int = Query(
        5,
        ge=1,
        description="Minimum duration for anomaly detection"
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of results"
    ),
):
    """
    Get recent voltage anomaly events.
    
    Detects sustained voltage sags (< 220V) lasting at least the specified duration.
    """
    # Default time range
    if end is None:
        end = datetime.utcnow()
    if start is None:
        start = end - timedelta(hours=24)
    
    query = f"""
    WITH 
    flagged_readings AS (
        SELECT
            meter_id,
            pole_id,
            event_ts,
            voltage_v,
            CASE WHEN voltage_v < 220 THEN 1 ELSE 0 END AS is_low_voltage
        FROM {get_table_ref('raw_meter_readings')}
        WHERE event_ts >= @start_time AND event_ts <= @end_time
    ),
    numbered AS (
        SELECT
            *,
            ROW_NUMBER() OVER (PARTITION BY meter_id ORDER BY event_ts) AS rn,
            ROW_NUMBER() OVER (PARTITION BY meter_id, is_low_voltage ORDER BY event_ts) AS rn_group
        FROM flagged_readings
    ),
    islands AS (
        SELECT
            *,
            rn - rn_group AS island_id
        FROM numbered
        WHERE is_low_voltage = 1
    ),
    sag_events AS (
        SELECT
            meter_id,
            pole_id,
            MIN(event_ts) AS event_start,
            MAX(event_ts) AS event_end,
            MIN(voltage_v) AS min_voltage_v,
            AVG(voltage_v) AS avg_voltage_v,
            TIMESTAMP_DIFF(MAX(event_ts), MIN(event_ts), SECOND) + 1 AS duration_seconds
        FROM islands
        GROUP BY meter_id, pole_id, island_id
    )
    SELECT
        meter_id,
        pole_id,
        event_start,
        event_end,
        duration_seconds,
        min_voltage_v,
        avg_voltage_v,
        CASE
            WHEN min_voltage_v < 200 THEN 'CRITICAL'
            WHEN min_voltage_v < 210 THEN 'WARNING'
            ELSE 'MINOR'
        END AS severity
    FROM sag_events
    WHERE duration_seconds >= @min_duration
    ORDER BY event_start DESC
    LIMIT @limit
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_time", "TIMESTAMP", start),
            bigquery.ScalarQueryParameter("end_time", "TIMESTAMP", end),
            bigquery.ScalarQueryParameter("min_duration", "INT64", min_duration_seconds),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
    )
    
    try:
        query_job = bq_client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        return [
            VoltageAnomaly(
                meter_id=row['meter_id'],
                pole_id=row['pole_id'],
                event_start=row['event_start'],
                event_end=row['event_end'],
                duration_seconds=row['duration_seconds'],
                min_voltage_v=round(row['min_voltage_v'], 2),
                avg_voltage_v=round(row['avg_voltage_v'], 2),
                severity=row['severity'],
            )
            for row in results
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@app.post("/dr/compute", response_model=DRComputeResponse)
async def compute_dr_performance(request: DRComputeRequest):
    """
    Compute demand response event performance.
    
    Compares actual load during the event window to historical baseline.
    """
    # Build pole filter
    pole_filter = ", ".join([f"'{p}'" for p in request.pole_ids])
    
    query = f"""
    WITH 
    actual_load AS (
        SELECT
            pole_id,
            EXTRACT(HOUR FROM event_ts) AS hour_of_day,
            CAST(FLOOR(EXTRACT(MINUTE FROM event_ts) / 5) * 5 AS INT64) AS minute_bucket,
            SUM(power_kw) AS actual_power_kw
        FROM {get_table_ref('raw_meter_readings')}
        WHERE 
            DATE(event_ts) = @event_date
            AND EXTRACT(HOUR FROM event_ts) >= @start_hour
            AND EXTRACT(HOUR FROM event_ts) < @end_hour
            AND pole_id IN ({pole_filter})
        GROUP BY pole_id, hour_of_day, minute_bucket
    ),
    baseline AS (
        SELECT
            pole_id,
            hour_of_day,
            minute_bucket,
            baseline_avg_kw
        FROM {get_table_ref('dr_5min_baseline')}
        WHERE pole_id IN ({pole_filter})
    ),
    joined AS (
        SELECT
            a.pole_id,
            a.actual_power_kw,
            COALESCE(b.baseline_avg_kw, 0) AS baseline_avg_kw,
            COALESCE(b.baseline_avg_kw, 0) - a.actual_power_kw AS reduction_kw
        FROM actual_load a
        LEFT JOIN baseline b
            ON a.pole_id = b.pole_id
            AND a.hour_of_day = b.hour_of_day
            AND a.minute_bucket = b.minute_bucket
    )
    SELECT
        pole_id,
        AVG(actual_power_kw) AS avg_actual_kw,
        AVG(baseline_avg_kw) AS avg_baseline_kw,
        AVG(reduction_kw) AS avg_reduction_kw,
        SAFE_DIVIDE(AVG(reduction_kw), AVG(baseline_avg_kw)) * 100 AS reduction_percent,
        SUM(reduction_kw) / 12 AS total_reduction_kwh
    FROM joined
    GROUP BY pole_id
    ORDER BY total_reduction_kwh DESC
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("event_date", "DATE", request.event_date),
            bigquery.ScalarQueryParameter("start_hour", "INT64", request.event_start_hour),
            bigquery.ScalarQueryParameter("end_hour", "INT64", request.event_end_hour),
        ]
    )
    
    try:
        query_job = bq_client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        poles = [
            DRPerformance(
                pole_id=row['pole_id'],
                avg_actual_kw=round(row['avg_actual_kw'] or 0, 2),
                avg_baseline_kw=round(row['avg_baseline_kw'] or 0, 2),
                avg_reduction_kw=round(row['avg_reduction_kw'] or 0, 2),
                reduction_percent=round(row['reduction_percent'] or 0, 2),
                total_reduction_kwh=round(row['total_reduction_kwh'] or 0, 3),
            )
            for row in results
        ]
        
        total_reduction = sum(p.total_reduction_kwh for p in poles)
        
        return DRComputeResponse(
            event_date=request.event_date,
            event_window=f"{request.event_start_hour}:00 - {request.event_end_hour}:00",
            poles=poles,
            total_reduction_kwh=round(total_reduction, 3),
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@app.get("/poles")
async def list_poles(limit: int = Query(100, ge=1, le=1000)):
    """List all poles with recent data."""
    query = f"""
    SELECT DISTINCT pole_id
    FROM {get_table_ref('raw_meter_readings')}
    WHERE event_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    ORDER BY pole_id
    LIMIT @limit
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
    )
    
    try:
        query_job = bq_client.query(query, job_config=job_config)
        results = list(query_job.result())
        return {"poles": [row['pole_id'] for row in results]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


# ===========================================================================
# Run with uvicorn
# ===========================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
