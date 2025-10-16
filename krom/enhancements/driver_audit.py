"""
driver_audit.py

Enhancement module for Krom: Audits installed drivers on Windows systems,
lists versions for critical devices (e.g., display and network adapters),
and provides update suggestions without performing any installations.

Associated with: After Repair stage.
CLI Flags: --driver-audit (enable), --suggest-updates (detailed recommendations).

Exports: run_driver_audit(args: argparse.Namespace, config: dict, logger: logging.Logger) -> None
"""

import csv
import io
import logging
import platform  # For platform checks
import subprocess
from pathlib import Path
from typing import Dict, List, Any
import datetime  # For timestamp in report
try:
    import ctypes  # For admin check on Windows
except ImportError:
    ctypes = None  # Fallback if not on Windows

# For online checks (add 'requests' to requirements.txt if enabling)
try:
    import requests
except ImportError:
    requests = None  # Offline fallback

def run_driver_audit(args, config: Dict[str, Any], logger: logging.Logger) -> None:
    """
    Run the driver audit enhancement.

    Args:
        args (argparse.Namespace): CLI arguments (e.g., args.offline, args.suggest_updates).
        config (Dict[str, Any]): Configuration dictionary.
        logger (logging.Logger): Logger instance for output.

    Returns:
        None
    """
    logger.info("=== Starting Driver Audit ===")
    
    # Early platform check: This enhancement is Windows-only
    if platform.system() != 'Windows':
        logger.warning("Driver audit is designed for Windows systems only; skipping on current platform.")
        return
    
    # Check if running as admin (Windows-specific)
    is_admin = False
    if ctypes:
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception as e:
            logger.debug(f"Admin check failed: {e}")
    if not is_admin:
        logger.error("Driver audit requires administrator privileges. Please run Krom as admin (right-click > Run as administrator). Skipping.")
        return
    
    # Respect CLI args over config
    offline = getattr(args, 'offline', config.get('offline', False))
    online_mode = not offline
    suggest_updates = getattr(args, 'suggest_updates', config.get('enhancements', {}).get('driver_audit', {}).get('suggest_updates', False))
    dry_run = getattr(args, 'dry_run', config.get('dry_run', False))
    
    if dry_run:
        logger.info("[Dry Run] Simulating driver audit; no real checks performed.")
    
    if not online_mode:
        logger.warning("Offline mode enabled. Audit will list local driver info only; no remote version checks.")
    
    # Load configurable critical keywords from config (fallback to defaults)
    default_keywords = ['display', 'video', 'graphics', 'network', 'ethernet', 'wifi', 'adapter']
    critical_keywords = config.get('enhancements', {}).get('driver_audit', {}).get('keywords', default_keywords)
    
    # Load suggestions from config (fallback to empty dict if not present)
    suggestions = config.get('enhancements', {}).get('driver_audit', {}).get('suggestions', {})
    
    if not suggestions:
        logger.warning("No suggestions loaded from config. Add them under enhancements.driver_audit.suggestions in YAML for better recommendations.")
    
    critical_drivers = []
    total_drivers = 0
    
    if not dry_run:
        # Use WMIC to get driver info in CSV format (Windows-specific)
        cmd = [
            'wmic', 'path', 'Win32_PnPSignedDriver',
            'get', 'DeviceName,DriverVersion,Manufacturer',
            '/format:csv'
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8-sig'  # Handle BOM if present
            )
            
            # Parse CSV output
            output = result.stdout.strip()
            if not output:
                logger.error("No output from WMIC; check command and privileges.")
                return
            
            # Use csv reader to parse (handles commas in names)
            reader = csv.reader(io.StringIO(output), delimiter=',')
            next(reader)  # Skip header row if present (WMIC adds node header)
            
            for row in reader:
                if len(row) < 3:  # Skip invalid rows
                    continue
                node, device_name, driver_version, manufacturer = row  # WMIC adds node column
                if device_name and driver_version and manufacturer:  # Valid driver
                    total_drivers += 1
                    # Check if critical
                    if any(keyword.lower() in device_name.lower() for keyword in critical_keywords):
                        critical_drivers.append({
                            'DeviceName': device_name,
                            'DriverVersion': driver_version,
                            'Manufacturer': manufacturer
                        })
            
            logger.info(f"Total installed drivers: {total_drivers}")
            if critical_drivers:
                logger.info(f"Critical drivers found (matching keywords {critical_keywords}): {len(critical_drivers)}")
                for driver in critical_drivers:
                    logger.info(f"  {driver['DeviceName']}: Version {driver['DriverVersion']} by {driver['Manufacturer']}")
            else:
                logger.info("No critical drivers matched the keywords. Expand keywords in config if needed.")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"WMIC command failed: {e.stderr}. Ensure Krom is run as administrator.")
            return
        except Exception as e:
            logger.error(f"Unexpected error in driver audit: {str(e)}. Check logs for details.")
            return
    else:
        # Dry-run simulation
        logger.info("[Dry Run] Would query WMIC for drivers.")
        critical_drivers = [{'DeviceName': 'Example Display Adapter', 'DriverVersion': '1.0', 'Manufacturer': 'NVIDIA'}]  # Mock

    # Suggestions section if enabled
    if suggest_updates:
        logger.info("Update suggestions (manual checks recommended to avoid issues):")
        logger.info("  - Use Windows Update (Settings > Update & Security).")
        logger.info("  - Check manufacturer sites for latest drivers.")
        
        for driver in critical_drivers:
            manuf_upper = driver['Manufacturer'].upper()
            matched_suggestion = next((url for key, url in suggestions.items() if key in manuf_upper), None)
            if matched_suggestion:
                logger.info(f"    {driver['DeviceName']}: Check {matched_suggestion}")
            else:
                logger.info(f"    {driver['DeviceName']}: Search for '{driver['Manufacturer']}' drivers online.")
        
        if online_mode and requests:
            logger.info("Online mode enabled: Checking for latest versions via APIs (where available).")
            for driver in critical_drivers:
                manuf = driver['Manufacturer'].upper()
                if 'NVIDIA' in manuf:
                    try:
                        response = requests.get('https://www.nvidia.com/Download/API/lookupValueSearch.aspx?TypeID=3&ParentID=105', timeout=10)  # Example NVIDIA API; adjust
                        latest_version = response.text  # Parse as needed
                        if latest_version and latest_version != driver['DriverVersion']:
                            logger.info(f"    Update available for {driver['DeviceName']}: Current {driver['DriverVersion']} -> Latest {latest_version}")
                        else:
                            logger.info(f"    {driver['DeviceName']}: Up to date or check manually.")
                    except requests.RequestException as e:
                        logger.warning(f"Online check for {driver['DeviceName']} failed: {e}")
                # Add more manuf checks (e.g., AMD, Intel) with real APIs
        elif online_mode:
            logger.warning("Online checks require 'requests' library. Add to requirements.txt and install.")
        else:
            logger.info("Enable online mode (disable --offline flag) for automated version comparisons.")

    # Save report to file (use configured logs path)
    logs_path = Path(config.get('paths', {}).get('logs', './logs'))
    report_path = logs_path / 'driver_audit_report.txt'
    report_path.parent.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().isoformat()
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"Krom Driver Audit Report - {timestamp}\n")
        f.write("=" * 40 + "\n\n")
        f.write(f"Total Drivers: {total_drivers}\n")
        f.write(f"Critical Drivers ({', '.join(critical_keywords)}):\n")
        for d in sorted(critical_drivers, key=lambda x: x['DeviceName']):
            f.write(f"- {d['DeviceName']}: Version {d['DriverVersion']} by {d['Manufacturer']}\n")
        if suggest_updates:
            f.write("\nSuggestions:\n")
            f.write("  - Run Windows Update.\n")
            for d in critical_drivers:
                manuf_upper = d['Manufacturer'].upper()
                url = next((url for key, url in suggestions.items() if key in manuf_upper), "Manual search recommended")
                f.write(f"  - {d['DeviceName']}: {url}\n")
    logger.info(f"Report saved to: {report_path}")
    
    logger.info("=== Driver Audit Completed ===")