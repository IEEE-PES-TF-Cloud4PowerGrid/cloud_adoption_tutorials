-- ============================================================================
-- Demand Response 5-Minute Baseline Computation
-- ============================================================================
-- Computes 5-minute average power consumption baselines per pole.
-- These baselines are used to measure DR event performance by comparing
-- actual load during an event to what was expected (baseline).
--
-- Baseline methodology: Average of similar 5-minute periods from the
-- past N days (excluding weekends and holidays for this example).
-- ============================================================================

-- Configuration
DECLARE baseline_lookback_days INT64 DEFAULT 10;

-- ============================================================================
-- Part 1: Current 5-minute aggregates (for recent data)
-- ============================================================================
CREATE OR REPLACE VIEW `PROJECT_ID.smart_grid_analytics.v_5min_aggregates` AS
SELECT
  pole_id,
  -- Truncate to 5-minute intervals
  TIMESTAMP_TRUNC(event_ts, MINUTE) AS minute_ts,
  CAST(FLOOR(EXTRACT(MINUTE FROM event_ts) / 5) * 5 AS INT64) AS minute_bucket,
  DATE(event_ts) AS event_date,
  EXTRACT(HOUR FROM event_ts) AS hour_of_day,
  EXTRACT(DAYOFWEEK FROM event_ts) AS day_of_week,
  
  -- Aggregate metrics
  COUNT(*) AS reading_count,
  COUNT(DISTINCT meter_id) AS meter_count,
  
  -- Power metrics
  SUM(power_kw) AS total_power_kw,
  AVG(power_kw) AS avg_power_kw,
  MAX(power_kw) AS max_power_kw,
  
  -- Voltage metrics
  AVG(voltage_v) AS avg_voltage_v,
  MIN(voltage_v) AS min_voltage_v,
  MAX(voltage_v) AS max_voltage_v,
  STDDEV(voltage_v) AS stddev_voltage_v,
  
  -- Current metrics
  SUM(current_a) AS total_current_a,
  AVG(current_a) AS avg_current_a,
  
  -- Reactive power
  SUM(reactive_kvar) AS total_reactive_kvar,
  AVG(freq_hz) AS avg_freq_hz

FROM `PROJECT_ID.smart_grid_analytics.raw_meter_readings`
GROUP BY 
  pole_id, 
  minute_ts, 
  minute_bucket, 
  event_date, 
  hour_of_day, 
  day_of_week;


-- ============================================================================
-- Part 2: Baseline calculation (historical average for same time-of-day)
-- ============================================================================
CREATE OR REPLACE TABLE `PROJECT_ID.smart_grid_analytics.dr_5min_baseline` AS
WITH 
-- Get 5-minute aggregates for baseline period
historical_5min AS (
  SELECT
    pole_id,
    EXTRACT(HOUR FROM event_ts) AS hour_of_day,
    CAST(FLOOR(EXTRACT(MINUTE FROM event_ts) / 5) * 5 AS INT64) AS minute_bucket,
    EXTRACT(DAYOFWEEK FROM event_ts) AS day_of_week,
    DATE(event_ts) AS event_date,
    SUM(power_kw) AS total_power_kw,
    COUNT(DISTINCT meter_id) AS meter_count
  FROM `PROJECT_ID.smart_grid_analytics.raw_meter_readings`
  WHERE 
    DATE(event_ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL baseline_lookback_days DAY)
    AND DATE(event_ts) < CURRENT_DATE()
    -- Exclude weekends for weekday baseline (adjust as needed)
    AND EXTRACT(DAYOFWEEK FROM event_ts) NOT IN (1, 7)
  GROUP BY pole_id, hour_of_day, minute_bucket, day_of_week, event_date
),

-- Calculate baseline statistics
baseline_stats AS (
  SELECT
    pole_id,
    hour_of_day,
    minute_bucket,
    
    -- Average baseline (mean of historical values)
    AVG(total_power_kw) AS baseline_avg_kw,
    
    -- Median baseline (more robust to outliers)
    APPROX_QUANTILES(total_power_kw, 100)[OFFSET(50)] AS baseline_median_kw,
    
    -- 10th and 90th percentiles for bounds
    APPROX_QUANTILES(total_power_kw, 100)[OFFSET(10)] AS baseline_p10_kw,
    APPROX_QUANTILES(total_power_kw, 100)[OFFSET(90)] AS baseline_p90_kw,
    
    -- Standard deviation for uncertainty
    STDDEV(total_power_kw) AS baseline_stddev_kw,
    
    -- Average meter count
    AVG(meter_count) AS avg_meter_count,
    
    -- Number of days used in baseline
    COUNT(DISTINCT event_date) AS baseline_days_count
    
  FROM historical_5min
  GROUP BY pole_id, hour_of_day, minute_bucket
)

SELECT
  pole_id,
  hour_of_day,
  minute_bucket,
  -- Create a time string for readability
  FORMAT('%02d:%02d', hour_of_day, minute_bucket) AS time_of_day,
  baseline_avg_kw,
  baseline_median_kw,
  baseline_p10_kw,
  baseline_p90_kw,
  baseline_stddev_kw,
  ROUND(avg_meter_count) AS avg_meter_count,
  baseline_days_count,
  CURRENT_TIMESTAMP() AS computed_at
FROM baseline_stats
ORDER BY pole_id, hour_of_day, minute_bucket;


-- ============================================================================
-- Part 3: DR Event Performance Query
-- ============================================================================
-- Use this query to compare actual load during a DR event to baseline.
-- Replace the event window parameters as needed.
-- ============================================================================

/*
-- Example: Analyze DR event from 2pm-6pm on a specific date
DECLARE event_date DATE DEFAULT DATE '2025-12-23';
DECLARE event_start_hour INT64 DEFAULT 14;  -- 2 PM
DECLARE event_end_hour INT64 DEFAULT 18;    -- 6 PM

WITH 
-- Get actual load during event
actual_load AS (
  SELECT
    pole_id,
    EXTRACT(HOUR FROM event_ts) AS hour_of_day,
    CAST(FLOOR(EXTRACT(MINUTE FROM event_ts) / 5) * 5 AS INT64) AS minute_bucket,
    SUM(power_kw) AS actual_power_kw,
    COUNT(DISTINCT meter_id) AS meter_count
  FROM `PROJECT_ID.smart_grid_analytics.raw_meter_readings`
  WHERE 
    DATE(event_ts) = event_date
    AND EXTRACT(HOUR FROM event_ts) >= event_start_hour
    AND EXTRACT(HOUR FROM event_ts) < event_end_hour
  GROUP BY pole_id, hour_of_day, minute_bucket
),

-- Join with baseline
event_performance AS (
  SELECT
    a.pole_id,
    a.hour_of_day,
    a.minute_bucket,
    a.actual_power_kw,
    b.baseline_avg_kw,
    b.baseline_median_kw,
    -- Load reduction (positive = reduced, negative = increased)
    b.baseline_avg_kw - a.actual_power_kw AS load_reduction_kw,
    -- Percent reduction
    SAFE_DIVIDE(b.baseline_avg_kw - a.actual_power_kw, b.baseline_avg_kw) * 100 AS reduction_percent
  FROM actual_load a
  LEFT JOIN `PROJECT_ID.smart_grid_analytics.dr_5min_baseline` b
    ON a.pole_id = b.pole_id
    AND a.hour_of_day = b.hour_of_day
    AND a.minute_bucket = b.minute_bucket
)

SELECT
  pole_id,
  -- Aggregate over the event window
  SUM(actual_power_kw) / COUNT(*) AS avg_actual_kw,
  SUM(baseline_avg_kw) / COUNT(*) AS avg_baseline_kw,
  SUM(load_reduction_kw) / COUNT(*) AS avg_reduction_kw,
  AVG(reduction_percent) AS avg_reduction_percent,
  -- Total energy reduction (kWh)
  SUM(load_reduction_kw) / 12 AS total_reduction_kwh  -- 5-min intervals = 1/12 hour
FROM event_performance
GROUP BY pole_id
ORDER BY avg_reduction_percent DESC;
*/
