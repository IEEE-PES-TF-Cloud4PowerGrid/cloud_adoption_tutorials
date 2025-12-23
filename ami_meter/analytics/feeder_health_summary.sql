-- ============================================================================
-- Feeder / Pole Health Summary
-- ============================================================================
-- Generates comprehensive health metrics for each pole/feeder.
-- Useful for operator dashboards and identifying problem areas.
--
-- Metrics include:
-- - Voltage quality (% low voltage, volatility)
-- - Power consumption patterns (peak, average)
-- - Data quality (missing readings, gaps)
-- ============================================================================

-- Configuration
DECLARE analysis_period_hours INT64 DEFAULT 24;

-- ============================================================================
-- Hourly Health Summary
-- ============================================================================
CREATE OR REPLACE VIEW `PROJECT_ID.smart_grid_analytics.v_pole_health_hourly` AS
WITH 
-- Base metrics per pole per hour
hourly_metrics AS (
  SELECT
    pole_id,
    DATE(event_ts) AS event_date,
    EXTRACT(HOUR FROM event_ts) AS hour_of_day,
    
    -- Reading counts
    COUNT(*) AS total_readings,
    COUNT(DISTINCT meter_id) AS active_meters,
    
    -- Voltage metrics
    AVG(voltage_v) AS avg_voltage_v,
    MIN(voltage_v) AS min_voltage_v,
    MAX(voltage_v) AS max_voltage_v,
    STDDEV(voltage_v) AS voltage_stddev,
    
    -- Voltage quality flags
    COUNTIF(voltage_v < 220) AS low_voltage_count,
    COUNTIF(voltage_v > 260) AS high_voltage_count,
    COUNTIF(ARRAY_LENGTH(quality_flags) > 0) AS flagged_readings,
    
    -- Power metrics
    SUM(power_kw) AS total_power_kw,
    AVG(power_kw) AS avg_power_per_meter_kw,
    MAX(power_kw) AS peak_meter_power_kw,
    
    -- Reactive power
    SUM(reactive_kvar) AS total_reactive_kvar,
    
    -- Frequency
    AVG(freq_hz) AS avg_freq_hz,
    MIN(freq_hz) AS min_freq_hz,
    MAX(freq_hz) AS max_freq_hz
    
  FROM `PROJECT_ID.smart_grid_analytics.raw_meter_readings`
  WHERE event_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL analysis_period_hours HOUR)
  GROUP BY pole_id, event_date, hour_of_day
),

-- Calculate expected readings (meters * 3600 seconds per hour)
expected_counts AS (
  SELECT
    pole_id,
    event_date,
    hour_of_day,
    active_meters * 3600 AS expected_readings
  FROM hourly_metrics
)

SELECT
  m.pole_id,
  m.event_date,
  m.hour_of_day,
  m.active_meters,
  m.total_readings,
  e.expected_readings,
  
  -- Data quality metrics
  ROUND(SAFE_DIVIDE(m.total_readings, e.expected_readings) * 100, 2) AS data_completeness_pct,
  e.expected_readings - m.total_readings AS missing_readings,
  
  -- Voltage quality metrics
  m.avg_voltage_v,
  m.min_voltage_v,
  m.max_voltage_v,
  m.voltage_stddev AS voltage_volatility,
  ROUND(SAFE_DIVIDE(m.low_voltage_count, m.total_readings) * 100, 2) AS low_voltage_pct,
  ROUND(SAFE_DIVIDE(m.high_voltage_count, m.total_readings) * 100, 2) AS high_voltage_pct,
  
  -- Power metrics
  m.total_power_kw,
  m.avg_power_per_meter_kw,
  m.peak_meter_power_kw,
  
  -- Power factor estimate (if reactive available)
  SAFE_DIVIDE(m.total_power_kw, 
    SQRT(POW(m.total_power_kw, 2) + POW(m.total_reactive_kvar, 2))
  ) AS estimated_power_factor,
  
  -- Frequency metrics
  m.avg_freq_hz,
  m.max_freq_hz - m.min_freq_hz AS freq_range_hz,
  
  -- Health score (0-100, higher is better)
  ROUND(
    (
      -- Data completeness component (25%)
      LEAST(SAFE_DIVIDE(m.total_readings, e.expected_readings), 1.0) * 25 +
      -- Voltage quality component (50%)
      (1 - SAFE_DIVIDE(m.low_voltage_count + m.high_voltage_count, m.total_readings)) * 50 +
      -- Voltage stability component (25%)
      GREATEST(0, 1 - m.voltage_stddev / 10) * 25
    ),
    1
  ) AS health_score

FROM hourly_metrics m
JOIN expected_counts e
  ON m.pole_id = e.pole_id
  AND m.event_date = e.event_date
  AND m.hour_of_day = e.hour_of_day
ORDER BY m.pole_id, m.event_date, m.hour_of_day;


-- ============================================================================
-- Daily Health Summary (Aggregated)
-- ============================================================================
CREATE OR REPLACE VIEW `PROJECT_ID.smart_grid_analytics.v_pole_health_daily` AS
SELECT
  pole_id,
  event_date,
  
  -- Meter stats
  MAX(active_meters) AS max_active_meters,
  AVG(active_meters) AS avg_active_meters,
  
  -- Data quality
  SUM(total_readings) AS total_readings,
  SUM(expected_readings) AS expected_readings,
  ROUND(SAFE_DIVIDE(SUM(total_readings), SUM(expected_readings)) * 100, 2) AS data_completeness_pct,
  
  -- Voltage quality (daily)
  AVG(avg_voltage_v) AS daily_avg_voltage_v,
  MIN(min_voltage_v) AS daily_min_voltage_v,
  MAX(max_voltage_v) AS daily_max_voltage_v,
  AVG(low_voltage_pct) AS avg_low_voltage_pct,
  MAX(low_voltage_pct) AS peak_low_voltage_hour_pct,
  
  -- Power (daily)
  SUM(total_power_kw) / 24 AS avg_hourly_power_kw,
  MAX(total_power_kw) AS peak_hour_power_kw,
  
  -- Health score
  AVG(health_score) AS avg_health_score,
  MIN(health_score) AS min_health_score,
  
  -- Problem hours count
  COUNTIF(health_score < 70) AS problem_hours_count

FROM `PROJECT_ID.smart_grid_analytics.v_pole_health_hourly`
GROUP BY pole_id, event_date
ORDER BY pole_id, event_date;


-- ============================================================================
-- Alert Query: Poles with Health Issues
-- ============================================================================
/*
SELECT 
  pole_id,
  event_date,
  hour_of_day,
  health_score,
  data_completeness_pct,
  low_voltage_pct,
  avg_voltage_v,
  min_voltage_v,
  CASE
    WHEN health_score < 50 THEN 'CRITICAL'
    WHEN health_score < 70 THEN 'WARNING'
    ELSE 'OK'
  END AS alert_level
FROM `PROJECT_ID.smart_grid_analytics.v_pole_health_hourly`
WHERE health_score < 70
ORDER BY health_score ASC, event_date DESC, hour_of_day DESC
LIMIT 100;
*/
