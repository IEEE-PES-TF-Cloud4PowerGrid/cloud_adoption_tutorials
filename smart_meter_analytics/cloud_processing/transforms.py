"""
Apache Beam Transforms for AMI 2.0 Data Processing

This module contains reusable PTransforms for parsing, validating,
and enriching AMI 2.0 smart meter telemetry data.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

import apache_beam as beam
from apache_beam.io.gcp.pubsub import PubsubMessage

logger = logging.getLogger(__name__)


# Schema for BigQuery table
BQ_SCHEMA = {
    'fields': [
        {'name': 'event_ts', 'type': 'TIMESTAMP', 'mode': 'REQUIRED'},
        {'name': 'ingest_ts', 'type': 'TIMESTAMP', 'mode': 'NULLABLE'},
        {'name': 'meter_id', 'type': 'STRING', 'mode': 'REQUIRED'},
        {'name': 'pole_id', 'type': 'STRING', 'mode': 'REQUIRED'},
        {'name': 'seq', 'type': 'INT64', 'mode': 'NULLABLE'},
        {'name': 'voltage_v', 'type': 'FLOAT64', 'mode': 'REQUIRED'},
        {'name': 'current_a', 'type': 'FLOAT64', 'mode': 'REQUIRED'},
        {'name': 'power_kw', 'type': 'FLOAT64', 'mode': 'REQUIRED'},
        {'name': 'reactive_kvar', 'type': 'FLOAT64', 'mode': 'NULLABLE'},
        {'name': 'freq_hz', 'type': 'FLOAT64', 'mode': 'NULLABLE'},
        {'name': 'quality_flags', 'type': 'STRING', 'mode': 'REPEATED'},
        {'name': 'network_profile', 'type': 'STRING', 'mode': 'NULLABLE'},
    ]
}

# Required fields for validation
REQUIRED_FIELDS = ['event_ts', 'meter_id', 'pole_id', 'voltage_v', 'current_a', 'power_kw']


class ParseJsonFn(beam.DoFn):
    """Parse JSON from Pub/Sub message bytes."""
    
    def process(self, element: PubsubMessage) -> Iterable[Tuple[str, Any]]:
        """
        Parse message and yield (status, data) tuple.
        
        Args:
            element: Pub/Sub message
            
        Yields:
            ('success', parsed_dict) or ('error', error_info)
        """
        try:
            data = element.data.decode('utf-8')
            parsed = json.loads(data)
            
            # Include attributes from message
            if element.attributes:
                parsed['_attributes'] = dict(element.attributes)
            
            yield ('success', parsed)
            
        except json.JSONDecodeError as e:
            error_info = {
                'error_type': 'json_decode_error',
                'error_message': str(e),
                'raw_data': element.data.decode('utf-8', errors='replace')[:1000],
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            yield ('error', error_info)
            
        except Exception as e:
            error_info = {
                'error_type': 'parse_error',
                'error_message': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            yield ('error', error_info)


class ValidateRecordFn(beam.DoFn):
    """Validate records against the telemetry schema."""
    
    def process(self, element: Dict[str, Any]) -> Iterable[Tuple[str, Any]]:
        """
        Validate record fields.
        
        Args:
            element: Parsed record dictionary
            
        Yields:
            ('success', validated_dict) or ('error', error_info)
        """
        errors = []
        
        # Check required fields
        for field in REQUIRED_FIELDS:
            if field not in element:
                errors.append(f"Missing required field: {field}")
        
        if errors:
            error_info = {
                'error_type': 'validation_error',
                'error_messages': errors,
                'record': element,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            yield ('error', error_info)
            return
        
        # Validate event_ts format
        try:
            event_ts = element['event_ts']
            if isinstance(event_ts, str):
                # Parse ISO format timestamp
                if event_ts.endswith('Z'):
                    event_ts = event_ts[:-1] + '+00:00'
                datetime.fromisoformat(event_ts)
        except (ValueError, TypeError) as e:
            error_info = {
                'error_type': 'timestamp_error',
                'error_message': f"Invalid event_ts: {e}",
                'record': element,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            yield ('error', error_info)
            return
        
        # Validate numeric fields
        numeric_fields = ['voltage_v', 'current_a', 'power_kw', 'reactive_kvar', 'freq_hz', 'seq']
        for field in numeric_fields:
            if field in element and element[field] is not None:
                try:
                    float(element[field])
                except (ValueError, TypeError):
                    errors.append(f"Invalid numeric value for {field}: {element[field]}")
        
        if errors:
            error_info = {
                'error_type': 'type_error',
                'error_messages': errors,
                'record': element,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            yield ('error', error_info)
            return
        
        yield ('success', element)


class EnrichRecordFn(beam.DoFn):
    """Enrich records with additional metadata."""
    
    def process(self, element: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        """
        Add ingestion timestamp and normalize fields.
        
        Args:
            element: Validated record dictionary
            
        Yields:
            Enriched record dictionary
        """
        # Add ingestion timestamp
        ingest_ts = datetime.now(timezone.utc).isoformat()
        
        # Normalize event_ts
        event_ts = element['event_ts']
        if isinstance(event_ts, str):
            if event_ts.endswith('Z'):
                event_ts = event_ts[:-1] + '+00:00'
        
        # Get network_profile from attributes if available
        network_profile = None
        if '_attributes' in element:
            network_profile = element['_attributes'].get('network_profile')
        
        # Build enriched record (matching BQ schema)
        enriched = {
            'event_ts': event_ts,
            'ingest_ts': ingest_ts,
            'meter_id': str(element['meter_id']),
            'pole_id': str(element['pole_id']),
            'seq': int(element.get('seq', 0)) if element.get('seq') is not None else None,
            'voltage_v': float(element['voltage_v']),
            'current_a': float(element['current_a']),
            'power_kw': float(element['power_kw']),
            'reactive_kvar': float(element['reactive_kvar']) if element.get('reactive_kvar') is not None else None,
            'freq_hz': float(element['freq_hz']) if element.get('freq_hz') is not None else None,
            'quality_flags': element.get('quality_flags', []),
            'network_profile': network_profile,
        }
        
        yield enriched


class FormatForGcsFn(beam.DoFn):
    """Format records as JSON lines for GCS storage."""
    
    def process(self, element: Dict[str, Any]) -> Iterable[str]:
        """
        Convert record to JSON line.
        
        Args:
            element: Record dictionary
            
        Yields:
            JSON string
        """
        yield json.dumps(element, default=str)


class FormatErrorFn(beam.DoFn):
    """Format error records for dead letter queue."""
    
    def process(self, element: Tuple[str, Any]) -> Iterable[bytes]:
        """
        Format error for DLQ.
        
        Args:
            element: (status, error_info) tuple
            
        Yields:
            JSON bytes for Pub/Sub
        """
        _, error_info = element
        yield json.dumps(error_info, default=str).encode('utf-8')


@beam.ptransform_fn
def ParseAndValidate(
    pcoll: beam.PCollection
) -> Tuple[beam.PCollection, beam.PCollection]:
    """
    Combined transform for parsing and validation.
    
    Args:
        pcoll: PCollection of Pub/Sub messages
        
    Returns:
        Tuple of (valid_records, error_records)
    """
    # Parse JSON
    parsed = pcoll | 'ParseJson' >> beam.ParDo(ParseJsonFn())
    
    # Split success and error
    parse_success = parsed | 'FilterParseSuccess' >> beam.Filter(lambda x: x[0] == 'success')
    parse_errors = parsed | 'FilterParseErrors' >> beam.Filter(lambda x: x[0] == 'error')
    
    # Extract parsed data
    parsed_data = parse_success | 'ExtractParsedData' >> beam.Map(lambda x: x[1])
    
    # Validate
    validated = parsed_data | 'ValidateRecords' >> beam.ParDo(ValidateRecordFn())
    
    # Split success and error
    valid_success = validated | 'FilterValidSuccess' >> beam.Filter(lambda x: x[0] == 'success')
    valid_errors = validated | 'FilterValidErrors' >> beam.Filter(lambda x: x[0] == 'error')
    
    # Extract validated data
    valid_data = valid_success | 'ExtractValidData' >> beam.Map(lambda x: x[1])
    
    # Combine all errors
    all_errors = (parse_errors, valid_errors) | 'FlattenErrors' >> beam.Flatten()
    
    return valid_data, all_errors


@beam.ptransform_fn
def EnrichRecords(pcoll: beam.PCollection) -> beam.PCollection:
    """
    Transform to enrich validated records.
    
    Args:
        pcoll: PCollection of validated record dicts
        
    Returns:
        PCollection of enriched records
    """
    return pcoll | 'Enrich' >> beam.ParDo(EnrichRecordFn())


class AggregateByWindow(beam.PTransform):
    """
    Aggregate records by time window.
    
    Computes per-pole statistics within fixed time windows.
    """
    
    def __init__(self, window_seconds: int = 60):
        """
        Initialize aggregation transform.
        
        Args:
            window_seconds: Window size in seconds
        """
        super().__init__()
        self.window_seconds = window_seconds
    
    def expand(self, pcoll: beam.PCollection) -> beam.PCollection:
        from apache_beam.transforms.window import FixedWindows
        
        def extract_key_value(record):
            """Extract (pole_id, record) for grouping."""
            return (record['pole_id'], record)
        
        def aggregate_readings(key_readings):
            """Aggregate readings for a pole."""
            pole_id, readings = key_readings
            readings_list = list(readings)
            
            if not readings_list:
                return None
            
            # Compute aggregates
            voltages = [r['voltage_v'] for r in readings_list]
            powers = [r['power_kw'] for r in readings_list]
            
            # Get window timestamp from first reading
            window_start = readings_list[0].get('event_ts', '')
            
            return {
                'pole_id': pole_id,
                'window_start': window_start,
                'reading_count': len(readings_list),
                'meter_count': len(set(r['meter_id'] for r in readings_list)),
                'avg_voltage_v': sum(voltages) / len(voltages),
                'min_voltage_v': min(voltages),
                'max_voltage_v': max(voltages),
                'total_power_kw': sum(powers),
                'avg_power_kw': sum(powers) / len(powers),
            }
        
        return (
            pcoll
            | 'Window' >> beam.WindowInto(FixedWindows(self.window_seconds))
            | 'KeyByPole' >> beam.Map(extract_key_value)
            | 'GroupByPole' >> beam.GroupByKey()
            | 'Aggregate' >> beam.Map(aggregate_readings)
            | 'FilterNone' >> beam.Filter(lambda x: x is not None)
        )
