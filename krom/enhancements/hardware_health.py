"""
hardware_health.py

Enhancement module for Krom: Performs hardware health checks on Windows systems,
including disk status (SMART via WMIC), battery health (if applicable),
memory usage, CPU load, and basic alerts for potential issues.

Associated with: Diagnostics (After Repair or Standalone).
CLI Flags: --hardware-health (enable), --standalone-hardware (run independently).

Exports: run_hardware_health(config: dict, logger: logging.Logger) -> None
"""

import logging
import subprocess
import platform
from pathlib import Path
from typing import Dict, Any

import psutil  # For CPU, memory, disk usage

def run_hardware_health(config: Dict[str, Any], logger: logging.Logger) -> None:
    """
    Run the hardware health check enhancement.

    Args:
        config (Dict[str, Any]): Configuration dictionary (e.g., {'alert_thresholds': {...}}).
        logger (logging.Logger): Logger instance for output.

    Returns:
        None
    """
    logger.info("=== Starting Hardware Health Check ===")
    
    # Default thresholds (can be overridden in config)
    thresholds = config.get('alert_thresholds', {
        'cpu_percent': 80.0,
        'memory_percent': 90.0,
        'disk_free_percent': 10.0,
        'battery_percent': 20.0
    })
    
    alerts = []
    is_laptop = 'battery' in psutil.sensors_batteries()
    
    try:
        # CPU Usage
        cpu_percent = psutil.cpu_percent(interval=1)
        logger.info(f"CPU Usage: {cpu_percent:.1f}%")
        if cpu_percent > thresholds['cpu_percent']:
            alerts.append(f"High CPU usage ({cpu_percent:.1f}%) - Consider monitoring processes.")
        
        # Memory Usage
        memory = psutil.virtual_memory()
        mem_percent = memory.percent
        logger.info(f"Memory Usage: {mem_percent:.1f}% ({memory.used // (1024**3):.1f} GB / {memory.total // (1024**3):.1f} GB)")
        if mem_percent > thresholds['memory_percent']:
            alerts.append(f"High memory usage ({mem_percent:.1f}%) - Close unnecessary applications.")
        
        # Disk Health (focus on C: drive)
        disk = psutil.disk_usage('C:\\')
        disk_free_percent = (disk.free / disk.total) * 100
        logger.info(f"System Disk (C:) Free Space: {disk_free_percent:.1f}% ({disk.free // (1024**3):.1f} GB free)")
        if disk_free_percent < thresholds['disk_free_percent']:
            alerts.append(f"Low disk space ({disk_free_percent:.1f}%) - Free up space to avoid issues.")
        
        # Disk SMART Status via WMIC
        cmd = ['wmic', 'diskdrive', 'get', 'Model,Status', '/format:table']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip()
        if output:
            logger.info("Disk Drive Status (SMART):")
            lines = output.splitlines()
            for line in lines[1:]:  # Skip header
                if line.strip() and 'OK' not in line:
                    model_status = line.strip()
                    alerts.append(f"Potential disk issue: {model_status}")
                    logger.warning(f"  - {model_status}")
                else:
                    logger.info(f"  - {line.strip()}")
        else:
            logger.warning("No disk status output from WMIC (ensure admin privileges).")
        
        # Battery Health (if laptop)
        if is_laptop:
            battery = psutil.sensors_battery()
            bat_percent = battery.percent
            logger.info(f"Battery Charge: {bat_percent:.1f}%")
            if bat_percent < thresholds['battery_percent']:
                alerts.append(f"Low battery ({bat_percent:.1f}%) - Plug in to avoid shutdown.")
            if battery.power_plugged:
                logger.info("Status: Plugged in")
            else:
                logger.info("Status: On battery")
        else:
            logger.info("Battery: Not detected (desktop or unavailable).")
        
        # Temperature Check (basic; advanced requires third-party tools like OpenHardwareMonitor)
        # Note: Win32_TemperatureProbe is often empty; stub for now
        temp_cmd = ['wmic', '/namespace:\\\\root\\wmi', 'path', 'MSAcpi_ThermalZoneTemperature', 'get', 'CurrentTemperature']
        try:
            temp_result = subprocess.run(temp_cmd, capture_output=True, text=True, check=True)
            if temp_result.stdout.strip():
                # Parse temperature (in tenths of Kelvin; convert to Celsius)
                temp_lines = temp_result.stdout.splitlines()
                for line in temp_lines[1:]:
                    if line.strip().isdigit():
                        temp_k = int(line.strip()) / 10.0 - 273.15  # Convert to Celsius
                        logger.info(f"Thermal Zone Temp: {temp_k:.1f}°C")
                        if temp_k > 80.0:  # Arbitrary high threshold
                            alerts.append(f"High temperature ({temp_k:.1f}°C) - Check cooling.")
            else:
                logger.info("Temperature: Not available via WMIC (install sensors for detailed monitoring).")
        except subprocess.CalledProcessError:
            logger.info("Temperature: Query failed (limited WMI support).")
        
        # Output Alerts
        if alerts:
            logger.warning("=== HEALTH ALERTS ===")
            for alert in alerts:
                logger.warning(f"  - {alert}")
        else:
            logger.info("No critical health issues detected.")
        
        # Save Report
        report_path = Path(config.get('logs', './logs')) / 'hardware_health_report.txt'
        report_path.parent.mkdir(exist_ok=True)
        with open(report_path, 'w') as f:
            f.write("Krom Hardware Health Report\n")
            f.write("=" * 35 + "\n\n")
            f.write(f"Timestamp: {config.get('run_timestamp', 'N/A')}\n")
            f.write(f"CPU: {cpu_percent:.1f}%\n")
            f.write(f"Memory: {mem_percent:.1f}%\n")
            f.write(f"Disk (C:): {disk_free_percent:.1f}%\n")
            if is_laptop:
                f.write(f"Battery: {bat_percent:.1f}%\n")
            if alerts:
                f.write("\nAlerts:\n")
                for alert in alerts:
                    f.write(f"  - {alert}\n")
            else:
                f.write("\nStatus: All checks passed.\n")
        logger.info(f"Report saved to: {report_path}")
        
    except Exception as e:
        logger.error(f"Error during hardware health check: {e}")
    
    logger.info("=== Hardware Health Check Completed ===")