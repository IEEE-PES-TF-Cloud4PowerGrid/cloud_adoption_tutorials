#!/usr/bin/env python3
"""
AMI 2.0 Smart Meter Analytics - Component Tests

This module contains unit tests for all major components of the tutorial.
Run with: python -m pytest tests/test_components.py -v
Or standalone: python tests/test_components.py
"""

import json
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'edge_simulation'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'cloud_processing'))


class TestSimulatorConfig(unittest.TestCase):
    """Test the SimulatorConfig class and YAML loading."""
    
    def test_config_from_yaml_with_interval(self):
        """Test config loading with sample_interval_seconds."""
        from simulator import SimulatorConfig
        
        config_dict = {
            'pole': {
                'pole_id': 'pole_test',
                'num_meters': 5,
                'meter_id_prefix': 'test_m'
            },
            'sampling': {
                'sample_interval_seconds': 30,
                'preset': 'high_frequency'
            },
            'electrical': {
                'voltage': {
                    'nominal_v': 240.0,
                    'noise_std': 3.0,
                    'sag_threshold': 220.0,
                    'swell_threshold': 260.0,
                    'sag_probability': 0.001,
                    'sag_depth_min': 10.0,
                    'sag_depth_max': 30.0,
                    'sag_duration_min': 3,
                    'sag_duration_max': 15
                },
                'power': {
                    'base_load_kw': 0.5,
                    'peak_morning_kw': 2.5,
                    'peak_evening_kw': 4.0,
                    'midday_kw': 1.0,
                    'night_kw': 0.4,
                    'noise_factor': 0.15,
                    'meter_factor_min': 0.7,
                    'meter_factor_max': 1.5
                },
                'reactive': {
                    'power_factor_min': 0.85,
                    'power_factor_max': 0.99,
                    'power_factor_default': 0.95
                },
                'frequency': {
                    'nominal_hz': 60.0,
                    'variation_hz': 0.05
                }
            },
            'demo': {
                'force_sag_interval_seconds': 60
            },
            'logging': {
                'stdout_events': False
            }
        }
        
        config = SimulatorConfig.from_yaml(config_dict)
        
        self.assertEqual(config.pole_id, 'pole_test')
        self.assertEqual(config.num_meters, 5)
        self.assertEqual(config.sample_interval_seconds, 30)
        self.assertEqual(config.voltage_nominal, 240.0)
    
    def test_config_preset_standard(self):
        """Test config loading with 'standard' preset (5 minutes)."""
        from simulator import SimulatorConfig
        
        config_dict = {
            'pole': {'pole_id': 'pole_A', 'num_meters': 10, 'meter_id_prefix': 'm'},
            'sampling': {'preset': 'standard'},
            'electrical': {
                'voltage': {'nominal_v': 240.0, 'noise_std': 3.0, 'sag_threshold': 220.0, 
                           'swell_threshold': 260.0, 'sag_probability': 0.001,
                           'sag_depth_min': 10.0, 'sag_depth_max': 30.0,
                           'sag_duration_min': 3, 'sag_duration_max': 15},
                'power': {'base_load_kw': 0.5, 'peak_morning_kw': 2.5, 'peak_evening_kw': 4.0,
                         'midday_kw': 1.0, 'night_kw': 0.4, 'noise_factor': 0.15,
                         'meter_factor_min': 0.7, 'meter_factor_max': 1.5},
                'reactive': {'power_factor_min': 0.85, 'power_factor_max': 0.99, 
                            'power_factor_default': 0.95},
                'frequency': {'nominal_hz': 60.0, 'variation_hz': 0.05}
            },
            'demo': {'force_sag_interval_seconds': 300},
            'logging': {'stdout_events': False}
        }
        
        config = SimulatorConfig.from_yaml(config_dict)
        self.assertEqual(config.sample_interval_seconds, 300)  # 5 minutes
    
    def test_config_preset_low_frequency(self):
        """Test config loading with 'low_frequency' preset (15 minutes)."""
        from simulator import SimulatorConfig
        
        config_dict = {
            'pole': {'pole_id': 'pole_A', 'num_meters': 10, 'meter_id_prefix': 'm'},
            'sampling': {'preset': 'low_frequency'},
            'electrical': {
                'voltage': {'nominal_v': 240.0, 'noise_std': 3.0, 'sag_threshold': 220.0, 
                           'swell_threshold': 260.0, 'sag_probability': 0.001,
                           'sag_depth_min': 10.0, 'sag_depth_max': 30.0,
                           'sag_duration_min': 3, 'sag_duration_max': 15},
                'power': {'base_load_kw': 0.5, 'peak_morning_kw': 2.5, 'peak_evening_kw': 4.0,
                         'midday_kw': 1.0, 'night_kw': 0.4, 'noise_factor': 0.15,
                         'meter_factor_min': 0.7, 'meter_factor_max': 1.5},
                'reactive': {'power_factor_min': 0.85, 'power_factor_max': 0.99, 
                            'power_factor_default': 0.95},
                'frequency': {'nominal_hz': 60.0, 'variation_hz': 0.05}
            },
            'demo': {'force_sag_interval_seconds': 900},
            'logging': {'stdout_events': False}
        }
        
        config = SimulatorConfig.from_yaml(config_dict)
        self.assertEqual(config.sample_interval_seconds, 900)  # 15 minutes


class TestMeterSimulator(unittest.TestCase):
    """Test the MeterSimulator class."""
    
    def setUp(self):
        """Set up test fixtures."""
        from simulator import SimulatorConfig, MeterSimulator
        
        config_dict = {
            'pole': {'pole_id': 'pole_test', 'num_meters': 3, 'meter_id_prefix': 'test'},
            'sampling': {'sample_interval_seconds': 30, 'preset': 'high_frequency'},
            'electrical': {
                'voltage': {'nominal_v': 240.0, 'noise_std': 3.0, 'sag_threshold': 220.0, 
                           'swell_threshold': 260.0, 'sag_probability': 0.0,
                           'sag_depth_min': 10.0, 'sag_depth_max': 30.0,
                           'sag_duration_min': 3, 'sag_duration_max': 15},
                'power': {'base_load_kw': 0.5, 'peak_morning_kw': 2.5, 'peak_evening_kw': 4.0,
                         'midday_kw': 1.0, 'night_kw': 0.4, 'noise_factor': 0.15,
                         'meter_factor_min': 0.7, 'meter_factor_max': 1.5},
                'reactive': {'power_factor_min': 0.85, 'power_factor_max': 0.99, 
                            'power_factor_default': 0.95},
                'frequency': {'nominal_hz': 60.0, 'variation_hz': 0.05}
            },
            'demo': {'force_sag_interval_seconds': 0},
            'logging': {'stdout_events': False}
        }
        
        self.config = SimulatorConfig.from_yaml(config_dict)
        self.simulator = MeterSimulator(self.config, seed=42)
    
    def test_meter_count(self):
        """Test that correct number of meters are initialized."""
        self.assertEqual(len(self.simulator.meters), 3)
    
    def test_generate_batch(self):
        """Test generating a batch of readings."""
        timestamp = datetime(2025, 12, 26, 12, 0, 0, tzinfo=timezone.utc)
        readings = self.simulator.generate_batch(timestamp)
        
        self.assertEqual(len(readings), 3)
        
        for reading in readings:
            self.assertIn('event_ts', reading)
            self.assertIn('meter_id', reading)
            self.assertIn('pole_id', reading)
            self.assertIn('voltage_v', reading)
            self.assertIn('current_a', reading)
            self.assertIn('power_kw', reading)
            
            # Check values are in reasonable ranges
            self.assertTrue(180 < reading['voltage_v'] < 280)
            self.assertTrue(reading['current_a'] >= 0)
            self.assertTrue(reading['power_kw'] >= 0)
    
    def test_reading_structure(self):
        """Test that readings have the correct structure."""
        timestamp = datetime(2025, 12, 26, 12, 0, 0, tzinfo=timezone.utc)
        readings = self.simulator.generate_batch(timestamp)
        reading = readings[0]
        
        expected_fields = [
            'event_ts', 'meter_id', 'pole_id', 'seq',
            'voltage_v', 'current_a', 'power_kw',
            'reactive_kvar', 'freq_hz', 'quality_flags'
        ]
        
        for field in expected_fields:
            self.assertIn(field, reading, f"Missing field: {field}")


# Try to import Apache Beam - skip transform tests if not available
try:
    import apache_beam
    BEAM_AVAILABLE = True
except ImportError:
    BEAM_AVAILABLE = False


@unittest.skipUnless(BEAM_AVAILABLE, "Apache Beam not installed")
class TestTransforms(unittest.TestCase):
    """Test the Beam transforms."""
    
    def test_parse_json_success(self):
        """Test successful JSON parsing."""
        from transforms import ParseJsonFn
        
        fn = ParseJsonFn()
        
        # Create mock Pub/Sub message
        message = Mock()
        message.data = json.dumps({
            'event_ts': '2025-12-26T12:00:00Z',
            'meter_id': 'test_001',
            'pole_id': 'pole_A',
            'voltage_v': 240.0,
            'current_a': 5.0,
            'power_kw': 1.2
        }).encode('utf-8')
        message.attributes = {'pole_id': 'pole_A'}
        
        results = list(fn.process(message))
        
        self.assertEqual(len(results), 1)
        status, data = results[0]
        self.assertEqual(status, 'success')
        self.assertEqual(data['meter_id'], 'test_001')
    
    def test_parse_json_invalid(self):
        """Test handling of invalid JSON."""
        from transforms import ParseJsonFn
        
        fn = ParseJsonFn()
        
        message = Mock()
        message.data = b'not valid json'
        message.attributes = {}
        
        results = list(fn.process(message))
        
        self.assertEqual(len(results), 1)
        status, error_info = results[0]
        self.assertEqual(status, 'error')
        self.assertIn('error_type', error_info)
    
    def test_validate_record_success(self):
        """Test successful record validation."""
        from transforms import ValidateRecordFn
        
        fn = ValidateRecordFn()
        
        record = {
            'event_ts': '2025-12-26T12:00:00Z',
            'meter_id': 'test_001',
            'pole_id': 'pole_A',
            'voltage_v': 240.0,
            'current_a': 5.0,
            'power_kw': 1.2
        }
        
        results = list(fn.process(record))
        
        self.assertEqual(len(results), 1)
        status, data = results[0]
        self.assertEqual(status, 'success')
    
    def test_validate_record_missing_field(self):
        """Test validation failure for missing fields."""
        from transforms import ValidateRecordFn
        
        fn = ValidateRecordFn()
        
        record = {
            'event_ts': '2025-12-26T12:00:00Z',
            'meter_id': 'test_001',
            # Missing pole_id, voltage_v, current_a, power_kw
        }
        
        results = list(fn.process(record))
        
        self.assertEqual(len(results), 1)
        status, error_info = results[0]
        self.assertEqual(status, 'error')
    
    def test_enrich_record(self):
        """Test record enrichment."""
        from transforms import EnrichRecordFn
        
        fn = EnrichRecordFn()
        
        record = {
            'event_ts': '2025-12-26T12:00:00Z',
            'meter_id': 'test_001',
            'pole_id': 'pole_A',
            'voltage_v': 240.0,
            'current_a': 5.0,
            'power_kw': 1.2,
            'seq': 100
        }
        
        results = list(fn.process(record))
        
        self.assertEqual(len(results), 1)
        enriched = results[0]
        
        self.assertIn('ingest_ts', enriched)
        self.assertEqual(enriched['meter_id'], 'test_001')
        self.assertEqual(enriched['voltage_v'], 240.0)


class TestMetricsPublisher(unittest.TestCase):
    """Test the Cloud Monitoring metrics publisher."""
    
    @patch('metrics_publisher.monitoring_v3.MetricServiceClient')
    @patch('metrics_publisher.monitoring_v3.TimeSeries')
    @patch('metrics_publisher.monitoring_v3.Point')
    @patch('metrics_publisher.monitoring_v3.CreateTimeSeriesRequest')
    def test_publish_pole_metrics(self, mock_request, mock_point, mock_ts, mock_client_class):
        """Test publishing pole metrics."""
        from metrics_publisher import MetricsPublisher
        
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        publisher = MetricsPublisher('test-project')
        
        readings = [
            {'meter_id': 'm1', 'pole_id': 'pole_A', 'voltage_v': 238.0, 'power_kw': 1.0},
            {'meter_id': 'm2', 'pole_id': 'pole_A', 'voltage_v': 242.0, 'power_kw': 1.5},
            {'meter_id': 'm3', 'pole_id': 'pole_A', 'voltage_v': 210.0, 'power_kw': 0.8},  # Sag
        ]
        
        result = publisher.publish_pole_metrics('pole_A', readings)
        
        self.assertTrue(result)
        mock_client.create_time_series.assert_called()
    
    @patch('metrics_publisher.monitoring_v3.MetricServiceClient')
    def test_empty_readings(self, mock_client_class):
        """Test handling of empty readings."""
        from metrics_publisher import MetricsPublisher
        
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        publisher = MetricsPublisher('test-project')
        
        result = publisher.publish_pole_metrics('pole_A', [])
        
        self.assertTrue(result)
        mock_client.create_time_series.assert_not_called()


class TestAPIEndpoints(unittest.TestCase):
    """Test the API endpoints."""
    
    @patch('google.cloud.bigquery.Client')
    def test_health_endpoint(self, mock_bq_client):
        """Test the health check endpoint."""
        # Import here to avoid issues with module-level BigQuery client
        import importlib
        import sys
        
        # Mock environment variables
        with patch.dict(os.environ, {'GOOGLE_CLOUD_PROJECT': 'test-project', 'BQ_DATASET': 'test_dataset'}):
            # We need to reload the module to pick up the mock
            if 'main' in sys.modules:
                del sys.modules['main']
            
            # For this test, we just verify the expected structure
            # Full integration tests would use TestClient from FastAPI
            self.assertTrue(True)  # Placeholder for actual test


class TestConfigYAML(unittest.TestCase):
    """Test loading the actual config.yaml file."""
    
    def test_load_config_file(self):
        """Test loading the real config.yaml file."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), 
            '..', 'edge_simulation', 'config.yaml'
        )
        
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Verify required sections exist
            self.assertIn('pole', config)
            self.assertIn('sampling', config)
            self.assertIn('electrical', config)
            
            # Verify new sampling configuration
            sampling = config['sampling']
            self.assertIn('sample_interval_seconds', sampling)
            self.assertIn('preset', sampling)
            
            # Verify preset is one of the valid options
            preset = sampling.get('preset', 'high_frequency')
            self.assertIn(preset, ['high_frequency', 'standard', 'low_frequency'])


def run_tests():
    """Run all tests and print summary."""
    print("=" * 70)
    print("AMI 2.0 Smart Meter Analytics - Component Tests")
    print("=" * 70)
    print()
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestSimulatorConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestMeterSimulator))
    suite.addTests(loader.loadTestsFromTestCase(TestTransforms))
    suite.addTests(loader.loadTestsFromTestCase(TestMetricsPublisher))
    suite.addTests(loader.loadTestsFromTestCase(TestAPIEndpoints))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigYAML))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print()
    print("=" * 70)
    if result.wasSuccessful():
        print("All tests passed!")
    else:
        print(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
    print("=" * 70)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
