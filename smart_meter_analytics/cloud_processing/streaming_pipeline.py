#!/usr/bin/env python3
"""
AMI 2.0 Streaming Pipeline

Apache Beam pipeline that:
1. Reads meter telemetry from Pub/Sub
2. Parses and validates JSON records
3. Enriches with ingestion metadata
4. Writes raw data to Cloud Storage (JSON lines)
5. Writes structured data to BigQuery (streaming inserts)
6. Routes invalid records to dead letter queue
7. Publishes real-time metrics to Cloud Monitoring

This pipeline is designed for Google Cloud Dataflow but can also
run locally with the DirectRunner for testing.
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import apache_beam as beam
from apache_beam.io import WriteToBigQuery
from apache_beam.io.gcp.pubsub import ReadFromPubSub, WriteToPubSub
from apache_beam.io.fileio import WriteToFiles, TextSink
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
from apache_beam.transforms.window import FixedWindows
from apache_beam.transforms.trigger import AfterWatermark, AfterProcessingTime, AccumulationMode

from transforms import (
    BQ_SCHEMA,
    ParseJsonFn,
    ValidateRecordFn,
    EnrichRecordFn,
    FormatForGcsFn,
    FormatErrorFn,
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class AMIPipelineOptions(PipelineOptions):
    """Custom pipeline options for AMI streaming."""
    
    @classmethod
    def _add_argparse_args(cls, parser: argparse.ArgumentParser):
        parser.add_argument(
            '--input_subscription',
            required=False,
            default=None,
            help='Pub/Sub subscription to read from (full path)'
        )
        parser.add_argument(
            '--output_bq_table',
            required=False,
            default=None,
            help='BigQuery table to write to (project:dataset.table)'
        )
        parser.add_argument(
            '--raw_archive_bucket',
            required=False,
            default=None,
            help='GCS bucket for raw archive'
        )
        parser.add_argument(
            '--raw_archive_prefix',
            default='raw/',
            help='Prefix for raw archive files in GCS'
        )
        parser.add_argument(
            '--dlq_topic',
            default=None,
            help='Pub/Sub topic for dead letter queue (optional)'
        )
        parser.add_argument(
            '--window_seconds',
            type=int,
            default=0,
            help='Window size for aggregation (0 to disable)'
        )
        parser.add_argument(
            '--agg_bq_table',
            default=None,
            help='BigQuery table for aggregated data (optional)'
        )
        parser.add_argument(
            '--enable_monitoring_metrics',
            action='store_true',
            default=False,
            help='Enable publishing custom metrics to Cloud Monitoring'
        )
        parser.add_argument(
            '--metrics_window_seconds',
            type=int,
            default=60,
            help='Window size for metrics aggregation (default: 60s)'
        )


def build_gcs_path(bucket: str, prefix: str) -> str:
    """Build GCS path with timestamp-based sharding."""
    # Window-based file naming will be handled by Beam
    return f'gs://{bucket}/{prefix}'


def run_pipeline(
    input_subscription: str,
    output_bq_table: str,
    raw_archive_bucket: str,
    raw_archive_prefix: str = 'raw/',
    dlq_topic: Optional[str] = None,
    window_seconds: int = 0,
    agg_bq_table: Optional[str] = None,
    enable_monitoring_metrics: bool = False,
    metrics_window_seconds: int = 60,
    pipeline_options: Optional[PipelineOptions] = None,
):
    """
    Build and run the streaming pipeline.
    
    Args:
        input_subscription: Full Pub/Sub subscription path
        output_bq_table: BigQuery table (project:dataset.table)
        raw_archive_bucket: GCS bucket name for raw archive
        raw_archive_prefix: Prefix for raw files
        dlq_topic: Optional Pub/Sub topic for DLQ
        window_seconds: Window size for aggregation (0 to disable)
        agg_bq_table: Optional BigQuery table for aggregated data
        enable_monitoring_metrics: Enable Cloud Monitoring custom metrics
        metrics_window_seconds: Window size for metrics aggregation
        pipeline_options: Beam pipeline options
    """
    logger.info(f"Starting AMI streaming pipeline")
    logger.info(f"  Input: {input_subscription}")
    logger.info(f"  Output BQ: {output_bq_table}")
    logger.info(f"  Raw Archive: gs://{raw_archive_bucket}/{raw_archive_prefix}")
    logger.info(f"  Cloud Monitoring Metrics: {'Enabled' if enable_monitoring_metrics else 'Disabled'}")
    
    with beam.Pipeline(options=pipeline_options) as p:
        
        # =====================================================================
        # Step 1: Read from Pub/Sub
        # =====================================================================
        messages = (
            p
            | 'ReadFromPubSub' >> ReadFromPubSub(
                subscription=input_subscription,
                with_attributes=True,
            )
        )
        
        # =====================================================================
        # Step 2: Parse JSON
        # =====================================================================
        parsed = messages | 'ParseJson' >> beam.ParDo(ParseJsonFn())
        
        # Split success and error
        parse_success = (
            parsed
            | 'FilterParseSuccess' >> beam.Filter(lambda x: x[0] == 'success')
            | 'ExtractParsedData' >> beam.Map(lambda x: x[1])
        )
        
        parse_errors = (
            parsed
            | 'FilterParseErrors' >> beam.Filter(lambda x: x[0] == 'error')
        )
        
        # =====================================================================
        # Step 3: Validate records
        # =====================================================================
        validated = parse_success | 'ValidateRecords' >> beam.ParDo(ValidateRecordFn())
        
        valid_records = (
            validated
            | 'FilterValidSuccess' >> beam.Filter(lambda x: x[0] == 'success')
            | 'ExtractValidData' >> beam.Map(lambda x: x[1])
        )
        
        valid_errors = (
            validated
            | 'FilterValidErrors' >> beam.Filter(lambda x: x[0] == 'error')
        )
        
        # Combine all errors
        all_errors = (
            (parse_errors, valid_errors)
            | 'FlattenErrors' >> beam.Flatten()
        )
        
        # =====================================================================
        # Step 4: Enrich records
        # =====================================================================
        enriched = valid_records | 'EnrichRecords' >> beam.ParDo(EnrichRecordFn())
        
        # =====================================================================
        # Step 5: Write raw archive to GCS
        # =====================================================================
        gcs_output_path = build_gcs_path(raw_archive_bucket, raw_archive_prefix)
        
        (
            enriched
            | 'WindowForGCS' >> beam.WindowInto(
                FixedWindows(60),  # 1-minute files
                trigger=AfterWatermark(early=AfterProcessingTime(30)),
                accumulation_mode=AccumulationMode.DISCARDING
            )
            | 'FormatForGCS' >> beam.ParDo(FormatForGcsFn())
            | 'WriteToGCS' >> WriteToFiles(
                path=gcs_output_path,
                sink=TextSink(),
                file_naming=beam.io.fileio.destination_prefix_naming()
            )
        )
        
        # =====================================================================
        # Step 6: Write to BigQuery
        # =====================================================================
        (
            enriched
            | 'WriteToBigQuery' >> WriteToBigQuery(
                table=output_bq_table,
                schema=BQ_SCHEMA,
                write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
                create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
                method=beam.io.WriteToBigQuery.Method.STREAMING_INSERTS,
            )
        )
        
        # =====================================================================
        # Step 7: Handle errors (DLQ)
        # =====================================================================
        if dlq_topic:
            (
                all_errors
                | 'FormatErrors' >> beam.ParDo(FormatErrorFn())
                | 'WriteToDLQ' >> WriteToPubSub(topic=dlq_topic)
            )
        # Note: errors are just dropped if no DLQ configured for now
        
        # =====================================================================
        # Step 8: Optional windowed aggregation
        # =====================================================================
        if window_seconds > 0 and agg_bq_table:
            from transforms import AggregateByWindow
            
            agg_schema = {
                'fields': [
                    {'name': 'pole_id', 'type': 'STRING', 'mode': 'REQUIRED'},
                    {'name': 'window_start', 'type': 'TIMESTAMP', 'mode': 'REQUIRED'},
                    {'name': 'reading_count', 'type': 'INT64', 'mode': 'REQUIRED'},
                    {'name': 'meter_count', 'type': 'INT64', 'mode': 'REQUIRED'},
                    {'name': 'avg_voltage_v', 'type': 'FLOAT64', 'mode': 'REQUIRED'},
                    {'name': 'min_voltage_v', 'type': 'FLOAT64', 'mode': 'REQUIRED'},
                    {'name': 'max_voltage_v', 'type': 'FLOAT64', 'mode': 'REQUIRED'},
                    {'name': 'total_power_kw', 'type': 'FLOAT64', 'mode': 'REQUIRED'},
                    {'name': 'avg_power_kw', 'type': 'FLOAT64', 'mode': 'REQUIRED'},
                ]
            }
            
            (
                enriched
                | 'AggregateByWindow' >> AggregateByWindow(window_seconds)
                | 'WriteAggToBigQuery' >> WriteToBigQuery(
                    table=agg_bq_table,
                    schema=agg_schema,
                    write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
                    create_disposition=beam.io.BigQueryDisposition.CREATE_IF_NEEDED,
                    method=beam.io.WriteToBigQuery.Method.STREAMING_INSERTS,
                )
            )
        
        # =====================================================================
        # Step 9: Publish metrics to Cloud Monitoring (optional)
        # =====================================================================
        if enable_monitoring_metrics:
            from transforms import PublishMonitoringMetricsFn
            
            # Extract project_id from output_bq_table (format: project:dataset.table)
            project_id = output_bq_table.split(':')[0] if ':' in output_bq_table else None
            
            if project_id:
                (
                    enriched
                    | 'WindowForMetrics' >> beam.WindowInto(
                        FixedWindows(metrics_window_seconds),
                        trigger=AfterWatermark(early=AfterProcessingTime(metrics_window_seconds // 2)),
                        accumulation_mode=AccumulationMode.DISCARDING
                    )
                    | 'KeyByPoleForMetrics' >> beam.Map(lambda x: (x.get('pole_id', 'unknown'), x))
                    | 'GroupByPoleForMetrics' >> beam.GroupByKey()
                    | 'PublishMetrics' >> beam.ParDo(PublishMonitoringMetricsFn(project_id))
                )
                logger.info(f"Cloud Monitoring metrics enabled with {metrics_window_seconds}s window")
            else:
                logger.warning("Could not extract project_id for Cloud Monitoring metrics")
    
    logger.info("Pipeline completed")


def main():
    """Main entry point."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='AMI 2.0 Streaming Pipeline'
    )
    
    # Add custom arguments
    parser.add_argument(
        '--input_subscription',
        required=True,
        help='Pub/Sub subscription (projects/PROJECT/subscriptions/SUB)'
    )
    parser.add_argument(
        '--output_bq_table',
        required=True,
        help='BigQuery table (project:dataset.table)'
    )
    parser.add_argument(
        '--raw_archive_bucket',
        required=True,
        help='GCS bucket for raw archive'
    )
    parser.add_argument(
        '--raw_archive_prefix',
        default='raw/',
        help='Prefix for raw archive files'
    )
    parser.add_argument(
        '--dlq_topic',
        default=None,
        help='Pub/Sub topic for dead letter queue'
    )
    parser.add_argument(
        '--window_seconds',
        type=int,
        default=0,
        help='Window size for aggregation (0 to disable)'
    )
    parser.add_argument(
        '--agg_bq_table',
        default=None,
        help='BigQuery table for aggregated data'
    )
    parser.add_argument(
        '--enable_monitoring_metrics',
        action='store_true',
        default=False,
        help='Enable publishing custom metrics to Cloud Monitoring'
    )
    parser.add_argument(
        '--metrics_window_seconds',
        type=int,
        default=60,
        help='Window size for metrics aggregation (default: 60s)'
    )
    
    # Parse known args (Beam will handle the rest)
    known_args, pipeline_args = parser.parse_known_args()
    
    # Create pipeline options
    pipeline_options = PipelineOptions(pipeline_args)
    
    # Set streaming mode
    pipeline_options.view_as(StandardOptions).streaming = True
    
    # Run the pipeline
    run_pipeline(
        input_subscription=known_args.input_subscription,
        output_bq_table=known_args.output_bq_table,
        raw_archive_bucket=known_args.raw_archive_bucket,
        raw_archive_prefix=known_args.raw_archive_prefix,
        dlq_topic=known_args.dlq_topic,
        window_seconds=known_args.window_seconds,
        agg_bq_table=known_args.agg_bq_table,
        enable_monitoring_metrics=known_args.enable_monitoring_metrics,
        metrics_window_seconds=known_args.metrics_window_seconds,
        pipeline_options=pipeline_options,
    )


if __name__ == '__main__':
    main()
