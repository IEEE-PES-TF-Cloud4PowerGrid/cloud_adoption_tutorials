-- ============================================================================
-- Voltage Anomaly Detection Query
-- ============================================================================
-- Detects sustained voltage sag events where voltage stays below threshold
-- for 5 or more consecutive seconds.
--
-- This uses a "gaps and islands" technique to identify consecutive low-voltage
-- readings and group them into events.
--
-- Output: meter_id, pole_id, event_start, event_end, min_voltage, duration_seconds
-- ============================================================================

-- Configuration (adjust these thresholds as needed)
DECLARE voltage_sag_threshold FLOAT64 DEFAULT 220.0;
DECLARE min_duration_seconds INT64 DEFAULT 5;

-- Main query using gaps-and-islands for sessionization
WITH 
-- Step 1: Flag low voltage readings
flagged_readings AS (
  SELECT
    meter_id,
    pole_id,
    event_ts,
    voltage_v,
    CASE WHEN voltage_v < voltage_sag_threshold THEN 1 ELSE 0 END AS is_low_voltage
  FROM `PROJECT_ID.smart_grid_analytics.raw_meter_readings`
  WHERE DATE(event_ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
),

-- Step 2: Assign row numbers and create grouping key
-- The grouping key changes when is_low_voltage changes
numbered AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY meter_id ORDER BY event_ts) AS rn,
    ROW_NUMBER() OVER (PARTITION BY meter_id, is_low_voltage ORDER BY event_ts) AS rn_group
  FROM flagged_readings
),

-- Step 3: Calculate island identifier (difference between row numbers)
islands AS (
  SELECT
    *,
    rn - rn_group AS island_id
  FROM numbered
  WHERE is_low_voltage = 1
),

-- Step 4: Aggregate islands into events
sag_events AS (
  SELECT
    meter_id,
    pole_id,
    island_id,
    MIN(event_ts) AS event_start,
    MAX(event_ts) AS event_end,
    MIN(voltage_v) AS min_voltage_v,
    MAX(voltage_v) AS max_voltage_v,
    AVG(voltage_v) AS avg_voltage_v,
    COUNT(*) AS reading_count,
    TIMESTAMP_DIFF(MAX(event_ts), MIN(event_ts), SECOND) + 1 AS duration_seconds
  FROM islands
  GROUP BY meter_id, pole_id, island_id
)

-- Step 5: Filter to events meeting minimum duration
SELECT
  meter_id,
  pole_id,
  event_start,
  event_end,
  duration_seconds,
  min_voltage_v,
  max_voltage_v,
  avg_voltage_v,
  reading_count,
  -- Severity classification
  CASE
    WHEN min_voltage_v < 200 THEN 'CRITICAL'
    WHEN min_voltage_v < 210 THEN 'WARNING'
    ELSE 'MINOR'
  END AS severity
FROM sag_events
WHERE duration_seconds >= min_duration_seconds
ORDER BY event_start DESC, meter_id;


-- ============================================================================
-- Alternative: Real-time detection (rolling window approach)
-- ============================================================================
-- This query uses a rolling window to detect when the last N seconds
-- have all been below threshold. Useful for near-real-time alerting.
-- ============================================================================

/*
WITH recent_readings AS (
  SELECT
    meter_id,
    pole_id,
    event_ts,
    voltage_v,
    -- Count low voltage readings in the last 5 seconds
    COUNTIF(voltage_v < 220.0) OVER (
      PARTITION BY meter_id 
      ORDER BY event_ts 
      RANGE BETWEEN INTERVAL 4 SECOND PRECEDING AND CURRENT ROW
    ) AS low_voltage_count_5s
  FROM `PROJECT_ID.smart_grid_analytics.raw_meter_readings`
  WHERE event_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 MINUTE)
)
SELECT DISTINCT
  meter_id,
  pole_id,
  event_ts AS alert_time,
  voltage_v AS current_voltage
FROM recent_readings
WHERE low_voltage_count_5s >= 5
ORDER BY event_ts DESC;
*/
