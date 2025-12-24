#!/usr/bin/env python3
"""
AMI 2.0 Gateway Relay / Publisher

This module acts as the pole gateway that:
1. Collects meter readings from the simulator
2. Simulates network backhaul effects (latency, jitter, drops)
3. Publishes data to Google Cloud Pub/Sub

The gateway simulates realistic network conditions for different
backhaul types: wired, 5G, LTE-M, and satellite connections.
"""

import argparse
import json
import logging
import os
import random
import signal
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml
from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.types import BatchSettings

from simulator import MeterSimulator, SimulatorConfig, load_config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


@dataclass
class NetworkProfile:
    """Network backhaul simulation parameters."""
    name: str
    latency_ms_min: int
    latency_ms_max: int
    jitter_ms: int
    drop_prob: float
    reorder_prob: float
    
    @classmethod
    def from_config(cls, name: str, config: Dict[str, Any]) -> 'NetworkProfile':
        """Create from config dictionary."""
        return cls(
            name=name,
            latency_ms_min=config.get('latency_ms_min', 20),
            latency_ms_max=config.get('latency_ms_max', 100),
            jitter_ms=config.get('jitter_ms', 30),
            drop_prob=config.get('drop_prob', 0.001),
            reorder_prob=config.get('reorder_prob', 0.001),
        )
    
    def get_latency_ms(self) -> int:
        """Get random latency with jitter."""
        base = random.randint(self.latency_ms_min, self.latency_ms_max)
        jitter = random.randint(-self.jitter_ms, self.jitter_ms)
        return max(1, base + jitter)
    
    def should_drop(self) -> bool:
        """Determine if message should be dropped."""
        return random.random() < self.drop_prob
    
    def should_reorder(self) -> bool:
        """Determine if message should be delayed for reordering."""
        return random.random() < self.reorder_prob


class GatewayStats:
    """Thread-safe statistics tracker for the gateway."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.messages_received = 0
        self.messages_published = 0
        self.messages_dropped = 0
        self.messages_reordered = 0
        self.publish_errors = 0
        self.start_time = time.time()
    
    def record_received(self, count: int = 1):
        with self._lock:
            self.messages_received += count
    
    def record_published(self, count: int = 1):
        with self._lock:
            self.messages_published += count
    
    def record_dropped(self, count: int = 1):
        with self._lock:
            self.messages_dropped += count
    
    def record_reordered(self, count: int = 1):
        with self._lock:
            self.messages_reordered += count
    
    def record_error(self, count: int = 1):
        with self._lock:
            self.publish_errors += count
    
    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            elapsed = time.time() - self.start_time
            return {
                "elapsed_seconds": round(elapsed, 1),
                "messages_received": self.messages_received,
                "messages_published": self.messages_published,
                "messages_dropped": self.messages_dropped,
                "messages_reordered": self.messages_reordered,
                "publish_errors": self.publish_errors,
                "publish_rate_per_sec": round(self.messages_published / max(1, elapsed), 2),
            }


class GatewayRelay:
    """
    Gateway relay that publishes meter readings to Pub/Sub.
    
    Simulates network effects and provides reliable delivery with retries.
    """
    
    def __init__(
        self,
        project_id: str,
        topic_name: str,
        network_profile: NetworkProfile,
        batch_settings: Optional[BatchSettings] = None,
    ):
        """
        Initialize the gateway relay.
        
        Args:
            project_id: GCP project ID
            topic_name: Pub/Sub topic name
            network_profile: Network simulation profile
            batch_settings: Optional Pub/Sub batch settings
        """
        self.project_id = project_id
        self.topic_name = topic_name
        self.topic_path = f"projects/{project_id}/topics/{topic_name}"
        self.network_profile = network_profile
        self.stats = GatewayStats()
        
        # Initialize Pub/Sub publisher with batching
        if batch_settings is None:
            batch_settings = BatchSettings(
                max_messages=100,
                max_bytes=1024 * 1024,  # 1 MB
                max_latency=0.5,  # 500ms
            )
        
        self.publisher = pubsub_v1.PublisherClient(
            batch_settings=batch_settings
        )
        
        # Reorder buffer for simulating out-of-order delivery
        self._reorder_buffer: deque = deque()
        self._reorder_delay_seconds = 2.0
        
        # Shutdown flag
        self._shutdown = threading.Event()
        
        logger.info(
            f"Initialized gateway relay: project={project_id}, "
            f"topic={topic_name}, network={network_profile.name}"
        )
    
    def _publish_callback(self, future):
        """Callback for async publish."""
        try:
            future.result()
            self.stats.record_published()
        except Exception as e:
            logger.error(f"Publish error: {e}")
            self.stats.record_error()
    
    def _process_reorder_buffer(self):
        """Process any messages that have been delayed for reordering."""
        now = time.time()
        while self._reorder_buffer:
            msg_time, message = self._reorder_buffer[0]
            if now - msg_time >= self._reorder_delay_seconds:
                self._reorder_buffer.popleft()
                self._do_publish(message)
            else:
                break
    
    def _do_publish(self, message: Dict[str, Any]):
        """Actually publish a message to Pub/Sub."""
        # Convert to JSON bytes
        data = json.dumps(message).encode('utf-8')
        
        # Add message attributes for filtering
        attributes = {
            'meter_id': message.get('meter_id', ''),
            'pole_id': message.get('pole_id', ''),
            'network_profile': self.network_profile.name,
        }
        
        # Publish asynchronously
        future = self.publisher.publish(
            self.topic_path,
            data=data,
            **attributes
        )
        future.add_done_callback(self._publish_callback)
    
    def publish(self, message: Dict[str, Any]) -> bool:
        """
        Publish a single message with network simulation.
        
        Args:
            message: Meter reading dictionary
            
        Returns:
            True if message was published (or queued for reorder)
        """
        self.stats.record_received()
        
        # Simulate network drop
        if self.network_profile.should_drop():
            self.stats.record_dropped()
            logger.debug(f"Dropped message for meter {message.get('meter_id')}")
            return False
        
        # Simulate network latency
        latency_ms = self.network_profile.get_latency_ms()
        time.sleep(latency_ms / 1000.0)
        
        # Simulate reordering
        if self.network_profile.should_reorder():
            self.stats.record_reordered()
            self._reorder_buffer.append((time.time(), message))
            logger.debug(f"Reordering message for meter {message.get('meter_id')}")
        else:
            self._do_publish(message)
        
        # Process any delayed messages
        self._process_reorder_buffer()
        
        return True
    
    def publish_batch(self, messages: List[Dict[str, Any]]) -> int:
        """
        Publish a batch of messages.
        
        Args:
            messages: List of meter reading dictionaries
            
        Returns:
            Number of messages successfully published
        """
        published = 0
        for message in messages:
            if self.publish(message):
                published += 1
        return published
    
    def flush(self):
        """Flush any pending messages."""
        # Process remaining reorder buffer
        while self._reorder_buffer:
            _, message = self._reorder_buffer.popleft()
            self._do_publish(message)
    
    def shutdown(self):
        """Graceful shutdown."""
        self._shutdown.set()
        self.flush()
        logger.info(f"Gateway stats: {json.dumps(self.stats.get_summary())}")
    
    def run_with_simulator(
        self,
        simulator: MeterSimulator,
        duration_seconds: int = 0,
        log_interval_seconds: int = 10,
    ):
        """
        Run the gateway with an integrated simulator.
        
        Args:
            simulator: MeterSimulator instance
            duration_seconds: Duration to run (0 for infinite)
            log_interval_seconds: Interval for logging stats
        """
        logger.info("Starting gateway relay with simulator...")
        
        last_log = time.time()
        
        try:
            for reading in simulator.stream_readings(duration_seconds):
                if self._shutdown.is_set():
                    break
                
                self.publish(reading)
                
                # Log stats periodically
                now = time.time()
                if now - last_log >= log_interval_seconds:
                    stats = self.stats.get_summary()
                    logger.info(f"Gateway stats: {json.dumps(stats)}")
                    last_log = now
                    
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.shutdown()


def load_gateway_config(config_path: str) -> Dict[str, Any]:
    """Load full configuration from YAML."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    """Main entry point for the gateway relay."""
    parser = argparse.ArgumentParser(
        description="AMI 2.0 Gateway Relay - Publishes meter data to Pub/Sub"
    )
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Path to configuration YAML file'
    )
    parser.add_argument(
        '--project',
        default=os.environ.get('GOOGLE_CLOUD_PROJECT'),
        help='GCP project ID (default: GOOGLE_CLOUD_PROJECT env var)'
    )
    parser.add_argument(
        '--topic',
        default=os.environ.get('PUBSUB_TOPIC'),
        help='Pub/Sub topic name (default: PUBSUB_TOPIC env var)'
    )
    parser.add_argument(
        '--duration', '-d',
        type=int,
        default=0,
        help='Duration to run in seconds (0 for infinite)'
    )
    parser.add_argument(
        '--network-profile',
        choices=['wired', '5g', 'lte_m', 'satellite'],
        default=None,
        help='Network profile to use (overrides config)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run simulator without publishing to Pub/Sub'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='Random seed for reproducibility'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Load configuration
    config_dict = load_gateway_config(args.config)
    
    # Get project and topic
    project_id = args.project
    topic_name = args.topic or config_dict.get('publish', {}).get('pubsub_topic', 'ami-meter-data')
    
    if not project_id and not args.dry_run:
        logger.error(
            "Project ID required. Set GOOGLE_CLOUD_PROJECT env var or use --project"
        )
        sys.exit(1)
    
    # Load simulator config
    sim_config = SimulatorConfig.from_yaml(config_dict)
    
    # Create simulator
    simulator = MeterSimulator(sim_config, seed=args.seed)
    
    if args.dry_run:
        # Just run simulator without publishing
        logger.info("Running in dry-run mode (no Pub/Sub publishing)")
        count = 0
        last_log = time.time()
        
        for reading in simulator.stream_readings(duration_seconds=args.duration):
            count += 1
            print(json.dumps(reading))
            
            now = time.time()
            if now - last_log >= 10:
                logger.info(f"Generated {count} readings")
                last_log = now
    else:
        # Get network profile
        network_config = config_dict.get('network', {})
        profile_name = args.network_profile or network_config.get('profile', '5g')
        profiles = network_config.get('profiles', {})
        
        if profile_name not in profiles:
            # Use defaults
            profile = NetworkProfile(
                name=profile_name,
                latency_ms_min=20,
                latency_ms_max=200,
                jitter_ms=50,
                drop_prob=0.001,
                reorder_prob=0.001,
            )
        else:
            profile = NetworkProfile.from_config(profile_name, profiles[profile_name])
        
        # Create gateway
        gateway = GatewayRelay(
            project_id=project_id,
            topic_name=topic_name,
            network_profile=profile,
        )
        
        # Handle signals
        def signal_handler(signum, frame):
            logger.info("Received shutdown signal")
            gateway.shutdown()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Run gateway with simulator
        gateway.run_with_simulator(
            simulator=simulator,
            duration_seconds=args.duration,
        )


if __name__ == "__main__":
    main()
