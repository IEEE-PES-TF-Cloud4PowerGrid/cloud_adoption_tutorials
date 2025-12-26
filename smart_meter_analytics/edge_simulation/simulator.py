#!/usr/bin/env python3
"""
AMI 2.0 Smart Meter Simulator

Generates realistic seconds-level synthetic meter data for the AMI 2.0 demo.
This module simulates multiple smart meters connected to a distribution pole,
producing voltage, current, and power readings at configurable intervals.

Features:
- Realistic daily load curves with morning/evening peaks
- Voltage sag/swell event injection for anomaly detection testing
- Per-meter variation factors for diversity
- Configurable sampling rate (default 1 Hz)
"""

import argparse
import json
import logging
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

import numpy as np
import yaml

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


@dataclass
class MeterState:
    """Maintains state for a single smart meter."""
    meter_id: str
    pole_id: str
    seq: int = 0
    meter_factor: float = 1.0  # Per-meter load variation
    power_factor: float = 0.95
    # Sag state
    in_sag: bool = False
    sag_remaining_seconds: int = 0
    sag_depth: float = 0.0


@dataclass
class SimulatorConfig:
    """Configuration for the meter simulator."""
    pole_id: str
    num_meters: int
    meter_id_prefix: str
    sample_interval_seconds: float  # Interval between readings (e.g., 30, 300, 900)
    sample_hz: float  # Deprecated: kept for backward compatibility
    
    # Voltage parameters
    voltage_nominal: float
    voltage_noise_std: float
    sag_threshold: float
    swell_threshold: float
    sag_probability: float
    sag_depth_min: float
    sag_depth_max: float
    sag_duration_min: int
    sag_duration_max: int
    
    # Power parameters
    base_load_kw: float
    peak_morning_kw: float
    peak_evening_kw: float
    midday_kw: float
    night_kw: float
    noise_factor: float
    meter_factor_min: float
    meter_factor_max: float
    
    # Reactive power
    pf_min: float
    pf_max: float
    pf_default: float
    
    # Frequency
    freq_nominal: float
    freq_variation: float
    
    # Demo mode
    force_sag_interval: int = 0
    stdout_events: bool = False
    
    @classmethod
    def from_yaml(cls, config_dict: Dict[str, Any]) -> 'SimulatorConfig':
        """Create config from parsed YAML dictionary."""
        pole = config_dict.get('pole', {})
        sampling = config_dict.get('sampling', {})
        electrical = config_dict.get('electrical', {})
        voltage = electrical.get('voltage', {})
        power = electrical.get('power', {})
        reactive = electrical.get('reactive', {})
        frequency = electrical.get('frequency', {})
        demo = config_dict.get('demo', {})
        logging_conf = config_dict.get('logging', {})
        
        # Handle sampling interval with preset support
        preset = sampling.get('preset', 'high_frequency')
        preset_intervals = {
            'high_frequency': 30,     # 30 seconds
            'standard': 300,          # 5 minutes  
            'low_frequency': 900,     # 15 minutes
        }
        
        # Priority: explicit sample_interval_seconds > preset > sample_hz (deprecated)
        sample_interval = sampling.get('sample_interval_seconds')
        if sample_interval is None:
            sample_interval = preset_intervals.get(preset, 30)
        
        # Backward compatibility: convert sample_hz if provided
        sample_hz = sampling.get('sample_hz')
        if sample_hz and sample_interval is None:
            sample_interval = 1.0 / sample_hz
        
        return cls(
            pole_id=pole.get('pole_id', 'pole_A'),
            num_meters=pole.get('num_meters', 10),
            meter_id_prefix=pole.get('meter_id_prefix', 'm'),
            sample_interval_seconds=sample_interval,
            sample_hz=1.0 / sample_interval if sample_interval > 0 else 1.0,
            voltage_nominal=voltage.get('nominal_v', 240.0),
            voltage_noise_std=voltage.get('noise_std', 3.0),
            sag_threshold=voltage.get('sag_threshold', 220.0),
            swell_threshold=voltage.get('swell_threshold', 260.0),
            sag_probability=voltage.get('sag_probability', 0.001),
            sag_depth_min=voltage.get('sag_depth_min', 10.0),
            sag_depth_max=voltage.get('sag_depth_max', 30.0),
            sag_duration_min=voltage.get('sag_duration_min', 3),
            sag_duration_max=voltage.get('sag_duration_max', 15),
            base_load_kw=power.get('base_load_kw', 0.5),
            peak_morning_kw=power.get('peak_morning_kw', 2.5),
            peak_evening_kw=power.get('peak_evening_kw', 4.0),
            midday_kw=power.get('midday_kw', 1.0),
            night_kw=power.get('night_kw', 0.4),
            noise_factor=power.get('noise_factor', 0.15),
            meter_factor_min=power.get('meter_factor_min', 0.7),
            meter_factor_max=power.get('meter_factor_max', 1.5),
            pf_min=reactive.get('power_factor_min', 0.85),
            pf_max=reactive.get('power_factor_max', 0.99),
            pf_default=reactive.get('power_factor_default', 0.95),
            freq_nominal=frequency.get('nominal_hz', 60.0),
            freq_variation=frequency.get('variation_hz', 0.05),
            force_sag_interval=demo.get('force_sag_interval_seconds', 0),
            stdout_events=logging_conf.get('stdout_events', False),
        )


class MeterSimulator:
    """
    Simulates multiple AMI 2.0 smart meters at a distribution pole.
    
    Generates realistic voltage, current, and power readings with:
    - Daily load curve patterns
    - Random noise and per-meter variation
    - Voltage sag/swell events for testing anomaly detection
    """
    
    def __init__(self, config: SimulatorConfig, seed: Optional[int] = None):
        """
        Initialize the simulator.
        
        Args:
            config: Simulator configuration
            seed: Random seed for reproducibility (optional)
        """
        self.config = config
        
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        
        # Initialize meter states
        self.meters: List[MeterState] = []
        for i in range(config.num_meters):
            meter_id = f"{config.meter_id_prefix}_{config.pole_id}_{i:04d}"
            meter_factor = random.uniform(config.meter_factor_min, config.meter_factor_max)
            power_factor = random.uniform(config.pf_min, config.pf_max)
            
            self.meters.append(MeterState(
                meter_id=meter_id,
                pole_id=config.pole_id,
                meter_factor=meter_factor,
                power_factor=power_factor,
            ))
        
        self._last_force_sag_time = time.time()
        self._readings_since_sag = 0  # Counter for interval-based sag triggering
        logger.info(
            f"Initialized simulator with {len(self.meters)} meters on pole {config.pole_id}, "
            f"interval={config.sample_interval_seconds}s"
        )
    
    def _get_load_curve_factor(self, hour: float) -> float:
        """
        Calculate load factor based on time of day.
        
        Implements a typical residential load curve with:
        - Morning peak (6-9 AM)
        - Midday valley (10 AM - 4 PM)
        - Evening peak (5-9 PM)
        - Night valley (10 PM - 5 AM)
        
        Args:
            hour: Hour of day (0-24, can include fractional hours)
            
        Returns:
            Load factor multiplier (0-1)
        """
        cfg = self.config
        
        # Normalize hour to 0-24
        hour = hour % 24
        
        # Piecewise linear load curve
        if 0 <= hour < 5:
            # Night valley
            return cfg.night_kw
        elif 5 <= hour < 6:
            # Transition to morning peak
            t = hour - 5
            return cfg.night_kw + t * (cfg.peak_morning_kw - cfg.night_kw)
        elif 6 <= hour < 9:
            # Morning peak
            return cfg.peak_morning_kw
        elif 9 <= hour < 10:
            # Transition to midday
            t = hour - 9
            return cfg.peak_morning_kw - t * (cfg.peak_morning_kw - cfg.midday_kw)
        elif 10 <= hour < 16:
            # Midday valley
            return cfg.midday_kw
        elif 16 <= hour < 17:
            # Transition to evening peak
            t = hour - 16
            return cfg.midday_kw + t * (cfg.peak_evening_kw - cfg.midday_kw)
        elif 17 <= hour < 21:
            # Evening peak
            return cfg.peak_evening_kw
        elif 21 <= hour < 22:
            # Transition to night
            t = hour - 21
            return cfg.peak_evening_kw - t * (cfg.peak_evening_kw - cfg.night_kw)
        else:
            # Night valley
            return cfg.night_kw
    
    def _should_start_sag(self, meter: MeterState) -> bool:
        """Check if a voltage sag should start for this meter."""
        if meter.in_sag:
            return False
        
        # Check for forced sag (demo mode)
        if self.config.force_sag_interval > 0:
            now = time.time()
            if now - self._last_force_sag_time >= self.config.force_sag_interval:
                self._last_force_sag_time = now
                return True
        
        # Random probability-based sag
        return random.random() < self.config.sag_probability
    
    def _update_sag_state(self, meter: MeterState) -> float:
        """
        Update voltage sag state and return voltage adjustment.
        
        Args:
            meter: Meter state to update
            
        Returns:
            Voltage adjustment (negative during sag)
        """
        if meter.in_sag:
            meter.sag_remaining_seconds -= 1
            if meter.sag_remaining_seconds <= 0:
                meter.in_sag = False
                meter.sag_depth = 0.0
                logger.debug(f"Sag ended for meter {meter.meter_id}")
                return 0.0
            return -meter.sag_depth
        
        if self._should_start_sag(meter):
            meter.in_sag = True
            meter.sag_depth = random.uniform(
                self.config.sag_depth_min,
                self.config.sag_depth_max
            )
            meter.sag_remaining_seconds = random.randint(
                self.config.sag_duration_min,
                self.config.sag_duration_max
            )
            logger.info(
                f"Sag started for meter {meter.meter_id}: "
                f"depth={meter.sag_depth:.1f}V, duration={meter.sag_remaining_seconds}s"
            )
            return -meter.sag_depth
        
        return 0.0
    
    def generate_reading(self, meter: MeterState, timestamp: datetime) -> Dict[str, Any]:
        """
        Generate a single meter reading.
        
        Args:
            meter: Meter state
            timestamp: Event timestamp
            
        Returns:
            Dictionary with meter reading data
        """
        cfg = self.config
        
        # Get hour with fractional component
        hour = timestamp.hour + timestamp.minute / 60.0 + timestamp.second / 3600.0
        
        # Calculate base power from load curve
        base_power = self._get_load_curve_factor(hour)
        
        # Apply per-meter factor and noise
        power_noise = 1.0 + random.gauss(0, cfg.noise_factor)
        power_kw = max(0.0, base_power * meter.meter_factor * power_noise)
        
        # Calculate voltage with noise and potential sag
        voltage_noise = random.gauss(0, cfg.voltage_noise_std)
        sag_adjustment = self._update_sag_state(meter)
        voltage_v = cfg.voltage_nominal + voltage_noise + sag_adjustment
        
        # Determine quality flags
        quality_flags = []
        if voltage_v < cfg.sag_threshold:
            quality_flags.append("voltage_sag")
        elif voltage_v > cfg.swell_threshold:
            quality_flags.append("voltage_swell")
        
        # Calculate current from power and voltage (P = V * I * PF)
        if voltage_v > 0 and power_kw > 0:
            current_a = (power_kw * 1000) / (voltage_v * meter.power_factor)
        else:
            current_a = 0.0
        
        # Calculate reactive power: Q = P * tan(acos(PF))
        pf_angle = math.acos(meter.power_factor)
        reactive_kvar = power_kw * math.tan(pf_angle)
        
        # Generate frequency with small variation
        freq_hz = cfg.freq_nominal + random.gauss(0, cfg.freq_variation)
        
        # Increment sequence number
        meter.seq += 1
        
        return {
            "event_ts": timestamp.isoformat(),
            "meter_id": meter.meter_id,
            "pole_id": meter.pole_id,
            "seq": meter.seq,
            "voltage_v": round(voltage_v, 2),
            "current_a": round(current_a, 3),
            "power_kw": round(power_kw, 3),
            "reactive_kvar": round(reactive_kvar, 3),
            "freq_hz": round(freq_hz, 3),
            "quality_flags": quality_flags,
        }
    
    def generate_batch(self, timestamp: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Generate readings for all meters at a given timestamp.
        
        Args:
            timestamp: Event timestamp (defaults to current UTC time)
            
        Returns:
            List of meter reading dictionaries
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        readings = []
        for meter in self.meters:
            reading = self.generate_reading(meter, timestamp)
            readings.append(reading)
            
            if self.config.stdout_events:
                print(json.dumps(reading))
        
        return readings
    
    def stream_readings(
        self,
        duration_seconds: int = 0
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Generate continuous stream of readings.
        
        Args:
            duration_seconds: Duration to run (0 for infinite)
            
        Yields:
            Individual meter readings
        """
        interval = self.config.sample_interval_seconds
        start_time = time.time()
        reading_count = 0
        
        logger.info(f"Starting simulation with {interval}s interval ({60/interval:.2f} readings/min per meter)")
        
        try:
            while True:
                cycle_start = time.time()
                
                # Check duration limit
                if duration_seconds > 0:
                    elapsed = cycle_start - start_time
                    if elapsed >= duration_seconds:
                        logger.info(f"Duration limit reached ({duration_seconds}s)")
                        break
                
                # Generate readings for this cycle
                timestamp = datetime.now(timezone.utc)
                readings = self.generate_batch(timestamp)
                reading_count += len(readings)
                
                for reading in readings:
                    yield reading
                
                # Sleep until next interval
                cycle_duration = time.time() - cycle_start
                sleep_time = max(0, interval - cycle_duration)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
        except KeyboardInterrupt:
            logger.info("Simulation stopped by user")
        finally:
            total_time = time.time() - start_time
            logger.info(
                f"Simulation complete: {reading_count} readings in {total_time:.1f}s "
                f"({reading_count/total_time:.1f} readings/s)"
            )


def load_config(config_path: str) -> SimulatorConfig:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        config_dict = yaml.safe_load(f)
    return SimulatorConfig.from_yaml(config_dict)


def main():
    """Main entry point for standalone simulator."""
    parser = argparse.ArgumentParser(
        description="AMI 2.0 Smart Meter Simulator"
    )
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Path to configuration YAML file'
    )
    parser.add_argument(
        '--duration', '-d',
        type=int,
        default=0,
        help='Duration to run in seconds (0 for infinite)'
    )
    parser.add_argument(
        '--stdout',
        action='store_true',
        help='Print each event to stdout as JSON'
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
    
    # Configure logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Load configuration
    config = load_config(args.config)
    if args.stdout:
        config.stdout_events = True
    
    # Create and run simulator
    simulator = MeterSimulator(config, seed=args.seed)
    
    # Stream readings (this will print stats periodically)
    count = 0
    last_log = time.time()
    log_interval = 10  # Log stats every 10 seconds
    
    for reading in simulator.stream_readings(duration_seconds=args.duration):
        count += 1
        now = time.time()
        if now - last_log >= log_interval:
            logger.info(f"Generated {count} readings")
            last_log = now


if __name__ == "__main__":
    main()
