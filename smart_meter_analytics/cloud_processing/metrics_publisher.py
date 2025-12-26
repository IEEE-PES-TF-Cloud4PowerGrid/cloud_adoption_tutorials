"""
Cloud Monitoring Metrics Publisher for AMI 2.0 Data

This module provides functionality to publish custom metrics from the
streaming pipeline to Google Cloud Monitoring for real-time dashboards.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud import monitoring_v3
from google.protobuf import timestamp_pb2

logger = logging.getLogger(__name__)


class MetricsPublisher:
    """
    Publishes custom AMI metrics to Google Cloud Monitoring.
    
    Metrics published:
    - voltage_avg: Average voltage at a pole
    - voltage_min: Minimum voltage at a pole
    - voltage_max: Maximum voltage at a pole
    - power_total_kw: Total power consumption at a pole
    - voltage_sag_count: Number of voltage sag events
    - health_score: Overall health score (0-100)
    - active_meter_count: Number of active meters
    """
    
    CUSTOM_METRIC_PREFIX = "custom.googleapis.com/ami"
    
    def __init__(self, project_id: str, batch_size: int = 200):
        """
        Initialize the metrics publisher.
        
        Args:
            project_id: GCP project ID
            batch_size: Maximum number of time series per write request
        """
        self.project_id = project_id
        self.project_name = f"projects/{project_id}"
        self.batch_size = batch_size
        self.client = monitoring_v3.MetricServiceClient()
        
        # Metric type definitions
        self.metric_types = {
            'voltage_avg': f"{self.CUSTOM_METRIC_PREFIX}/voltage_avg",
            'voltage_min': f"{self.CUSTOM_METRIC_PREFIX}/voltage_min",
            'voltage_max': f"{self.CUSTOM_METRIC_PREFIX}/voltage_max",
            'power_total_kw': f"{self.CUSTOM_METRIC_PREFIX}/power_total_kw",
            'voltage_sag_count': f"{self.CUSTOM_METRIC_PREFIX}/voltage_sag_count",
            'health_score': f"{self.CUSTOM_METRIC_PREFIX}/health_score",
            'active_meter_count': f"{self.CUSTOM_METRIC_PREFIX}/active_meter_count",
        }
        
        logger.info(f"Initialized MetricsPublisher for project {project_id}")
    
    def _create_time_series(
        self,
        metric_type: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[datetime] = None,
        value_type: str = 'double'
    ) -> monitoring_v3.TimeSeries:
        """
        Create a TimeSeries object for a single metric point.
        
        Args:
            metric_type: Full metric type path
            value: Metric value
            labels: Metric labels (e.g., pole_id)
            timestamp: Point timestamp (defaults to now)
            value_type: 'double' or 'int64'
            
        Returns:
            TimeSeries protobuf object
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        series = monitoring_v3.TimeSeries()
        series.metric.type = metric_type
        
        # Add labels
        for key, val in labels.items():
            series.metric.labels[key] = str(val)
        
        # Set resource type to global (custom metrics)
        series.resource.type = "global"
        series.resource.labels["project_id"] = self.project_id
        
        # Create the data point
        point = monitoring_v3.Point()
        
        # Set timestamp
        seconds = int(timestamp.timestamp())
        nanos = int((timestamp.timestamp() - seconds) * 1e9)
        point.interval.end_time.seconds = seconds
        point.interval.end_time.nanos = nanos
        
        # Set value
        if value_type == 'int64':
            point.value.int64_value = int(value)
        else:
            point.value.double_value = float(value)
        
        series.points.append(point)
        
        return series
    
    def publish_pole_metrics(
        self,
        pole_id: str,
        readings: List[Dict[str, Any]],
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Publish aggregated metrics for a pole from a batch of readings.
        
        Args:
            pole_id: Pole identifier
            readings: List of meter reading dictionaries
            timestamp: Metric timestamp (defaults to now)
            
        Returns:
            True if successful, False otherwise
        """
        if not readings:
            return True
        
        try:
            # Calculate aggregates
            voltages = [r['voltage_v'] for r in readings if 'voltage_v' in r]
            powers = [r['power_kw'] for r in readings if 'power_kw' in r]
            
            if not voltages or not powers:
                logger.warning(f"No valid readings for pole {pole_id}")
                return False
            
            voltage_avg = sum(voltages) / len(voltages)
            voltage_min = min(voltages)
            voltage_max = max(voltages)
            power_total = sum(powers)
            
            # Count voltage sags (below 220V threshold)
            sag_threshold = 220.0
            voltage_sag_count = sum(1 for v in voltages if v < sag_threshold)
            
            # Calculate health score (% of readings within normal range)
            normal_count = sum(1 for v in voltages if 220 <= v <= 260)
            health_score = (normal_count / len(voltages)) * 100
            
            # Count unique meters
            meter_ids = set(r.get('meter_id', '') for r in readings)
            active_meter_count = len(meter_ids)
            
            labels = {'pole_id': pole_id}
            
            # Create time series for each metric
            time_series_list = [
                self._create_time_series(
                    self.metric_types['voltage_avg'],
                    voltage_avg,
                    labels,
                    timestamp
                ),
                self._create_time_series(
                    self.metric_types['voltage_min'],
                    voltage_min,
                    labels,
                    timestamp
                ),
                self._create_time_series(
                    self.metric_types['voltage_max'],
                    voltage_max,
                    labels,
                    timestamp
                ),
                self._create_time_series(
                    self.metric_types['power_total_kw'],
                    power_total,
                    labels,
                    timestamp
                ),
                self._create_time_series(
                    self.metric_types['voltage_sag_count'],
                    voltage_sag_count,
                    labels,
                    timestamp,
                    value_type='int64'
                ),
                self._create_time_series(
                    self.metric_types['health_score'],
                    health_score,
                    labels,
                    timestamp
                ),
                self._create_time_series(
                    self.metric_types['active_meter_count'],
                    active_meter_count,
                    labels,
                    timestamp,
                    value_type='int64'
                ),
            ]
            
            # Write time series in batches
            for i in range(0, len(time_series_list), self.batch_size):
                batch = time_series_list[i:i + self.batch_size]
                request = monitoring_v3.CreateTimeSeriesRequest(
                    name=self.project_name,
                    time_series=batch
                )
                self.client.create_time_series(request=request)
            
            logger.debug(f"Published {len(time_series_list)} metrics for pole {pole_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error publishing metrics for pole {pole_id}: {e}")
            return False
    
    def publish_batch(
        self,
        readings_by_pole: Dict[str, List[Dict[str, Any]]],
        timestamp: Optional[datetime] = None
    ) -> Dict[str, bool]:
        """
        Publish metrics for multiple poles.
        
        Args:
            readings_by_pole: Dictionary mapping pole_id to list of readings
            timestamp: Metric timestamp (defaults to now)
            
        Returns:
            Dictionary mapping pole_id to success status
        """
        results = {}
        for pole_id, readings in readings_by_pole.items():
            results[pole_id] = self.publish_pole_metrics(pole_id, readings, timestamp)
        return results


class MetricsPublisherDoFn:
    """
    Apache Beam DoFn wrapper for publishing metrics.
    
    Use this in a Beam pipeline to publish metrics as data flows through.
    """
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.publisher = None
        self._buffer: Dict[str, List[Dict[str, Any]]] = {}
        self._last_flush = time.time()
        self._flush_interval = 60  # Flush every 60 seconds
    
    def setup(self):
        """Initialize the publisher (called once per worker)."""
        self.publisher = MetricsPublisher(self.project_id)
    
    def process(self, element: Dict[str, Any]):
        """
        Process a single record and buffer for metric publishing.
        
        Args:
            element: Enriched meter reading
        """
        pole_id = element.get('pole_id', 'unknown')
        
        if pole_id not in self._buffer:
            self._buffer[pole_id] = []
        self._buffer[pole_id].append(element)
        
        # Check if we should flush
        now = time.time()
        if now - self._last_flush >= self._flush_interval:
            self._flush()
            self._last_flush = now
        
        # Pass through the element unchanged
        yield element
    
    def _flush(self):
        """Flush buffered metrics to Cloud Monitoring."""
        if self.publisher and self._buffer:
            self.publisher.publish_batch(self._buffer)
            self._buffer.clear()
    
    def teardown(self):
        """Cleanup (called on worker shutdown)."""
        self._flush()


# Standalone utility function for simpler use cases
def publish_metrics_from_readings(
    project_id: str,
    readings: List[Dict[str, Any]]
) -> bool:
    """
    Convenience function to publish metrics from a list of readings.
    
    Args:
        project_id: GCP project ID
        readings: List of meter reading dictionaries
        
    Returns:
        True if all metrics published successfully
    """
    publisher = MetricsPublisher(project_id)
    
    # Group readings by pole
    readings_by_pole: Dict[str, List[Dict[str, Any]]] = {}
    for reading in readings:
        pole_id = reading.get('pole_id', 'unknown')
        if pole_id not in readings_by_pole:
            readings_by_pole[pole_id] = []
        readings_by_pole[pole_id].append(reading)
    
    results = publisher.publish_batch(readings_by_pole)
    return all(results.values())
