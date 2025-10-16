"""
privacy_scrub.py

Enhancement module for Krom: Performs privacy scrubbing by blocking tracking hosts,
clearing DNS cache, disabling telemetry, and cleaning browser tracking data.

Associated with: After De-Bloat stage.
CLI Flags: --privacy-scrub (enable), --hosts-file <path>, --browsers <chrome,firefox>.

Exports: run_privacy_scrub(config: dict, logger: logging.Logger) -> None
"""

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List
try:
    import ctypes  # For admin check on Windows
except ImportError:
    ctypes = None
# Optional: For online updates (add 'requests' to requirements.txt if using)
# import requests

def run_privacy_scrub(config: Dict[str, Any], logger: logging.Logger) -> None:
    """
    Run the privacy scrub enhancement.

    Args:
        config (Dict[str, Any]): Configuration dictionary.
        logger (logging.Logger): Logger instance for output.

    Returns:
        None
    """
    logger.info("=== Starting Privacy Scrub ===")
    
    # Load config for privacy_scrub
    ps_config = config.get('enhancements', {}).get('privacy_scrub', {})
    enabled = ps_config.get('enabled', False)
    if not enabled:
        logger.info("Privacy scrub not enabled; skipping.")
        return
    
    # Early platform check: Optimized for Windows
    if platform.system() != 'Windows':
        logger.warning("Privacy scrub is optimized for Windows; some features may not apply on other platforms.")
    
    # Admin check
    is_admin = False
    if ctypes and platform.system() == 'Windows':
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception as e:
            logger.debug(f"Admin check failed: {e}")
    if not is_admin:
        logger.error("Privacy scrub requires administrator privileges for some operations (e.g., hosts file). Run as admin. Skipping risky parts.")
    
    hosts_blocks = ps_config.get('hosts_blocks', [])
    browsers = ps_config.get('browsers', ['chrome', 'firefox', 'edge'])
    clear_dns = ps_config.get('clear_dns', True)
    disable_telemetry = ps_config.get('disable_telemetry', True)
    hosts_file = Path(ps_config.get('hosts_file', r'C:\Windows\System32\drivers\etc\hosts'))
    online_update = ps_config.get('online_update', False)
    dry_run = config.get('dry_run', False)
    offline = config.get('offline', False)
    
    # Fetch additional hosts if online_update and not offline
    if online_update and not offline:
        logger.info("Online update enabled; fetching latest hosts blocks (stub - implement with requests).")
        # Example stub:
        # try:
        #     response = requests.get('https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts')
        #     if response.status_code == 200:
        #         fetched = [line.split()[1] for line in response.text.splitlines() if line.startswith('0.0.0.0')]
        #         hosts_blocks.extend(fetched)
        #         hosts_blocks = list(set(hosts_blocks))  # Dedupe
        # except requests.RequestException as e:
        #     logger.warning(f"Failed to fetch hosts: {e}")
    else:
        logger.info("Using configured hosts blocks only (offline mode or update disabled).")
    
    # Backup hosts file and browser data
    backups_path = Path(config.get('paths', {}).get('backups', './backups'))
    backups_path.mkdir(exist_ok=True)
    if hosts_file.exists():
        shutil.copy(hosts_file, backups_path / 'hosts_backup')
        logger.info(f"Backed up hosts file to: {backups_path / 'hosts_backup'}")
    for browser in browsers:
        browser_paths = _get_browser_paths(browser)
        for bp in browser_paths:
            if bp.exists():
                shutil.copytree(bp, backups_path / f'{browser}_backup', dirs_exist_ok=True)
                logger.info(f"Backed up {browser} data to: {backups_path / f'{browser}_backup'}")
    
    # Dry-run simulation
    if dry_run:
        logger.info("Dry-run mode: Simulating privacy scrub without changes.")
        logger.info(f"Would block {len(hosts_blocks)} hosts in {hosts_file}.")
        if clear_dns:
            logger.info("Would clear DNS cache.")
        if disable_telemetry:
            logger.info("Would disable telemetry services and tasks.")
        for browser in browsers:
            logger.info(f"Would clean tracking data for {browser}.")
        logger.info("=== Privacy Scrub Simulated (Dry-Run) ===")
        return
    
    # Apply scrubs
    report = {'blocked_hosts': 0, 'cleared_browsers': {}, 'disabled_telemetry': []}
    
    if hosts_blocks and hosts_file.exists() and is_admin:
        report['blocked_hosts'] = _edit_hosts_file(hosts_blocks, hosts_file, logger)
    
    if clear_dns and platform.system() == 'Windows':
        _clear_dns_cache(logger)
    
    if disable_telemetry and is_admin and platform.system() == 'Windows':
        report['disabled_telemetry'] = _disable_telemetry(logger)
    
    for browser in browsers:
        cleared = _clean_browser(browser, logger)
        report['cleared_browsers'][browser] = cleared
    
    # Generate report
    logs_path = Path(config.get('paths', {}).get('logs', './logs'))
    report_path = logs_path / 'privacy_scrub_report.txt'
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("Krom Privacy Scrub Report\n")
        f.write("=" * 30 + "\n\n")
        f.write(f"Blocked Hosts: {report['blocked_hosts']}\n")
        f.write(f"Disabled Telemetry Items: {len(report['disabled_telemetry'])}\n")
        for browser, count in report['cleared_browsers'].items():
            f.write(f"Cleared {browser} Items: {count}\n")
    logger.info(f"Report saved to: {report_path}")
    
    logger.info("=== Privacy Scrub Completed ===")

def _edit_hosts_file(blocks: List[str], hosts_path: Path, logger: logging.Logger) -> int:
    """Append blocks to hosts file if not present."""
    added = 0
    try:
        with open(hosts_path, 'r+', encoding='utf-8') as f:
            content = f.read()
            f.seek(0, os.SEEK_END)
            for domain in blocks:
                if domain not in content:
                    f.write(f"\n0.0.0.0 {domain}")
                    added += 1
        logger.info(f"Added {added} new blocks to hosts file.")
        return added
    except PermissionError:
        logger.error("Permission denied for hosts file. Skipping.")
        return 0
    except Exception as e:
        logger.error(f"Error editing hosts file: {str(e)}")
        return 0

def _clear_dns_cache(logger: logging.Logger) -> None:
    """Clear DNS cache."""
    try:
        subprocess.run(['ipconfig', '/flushdns'], check=True, capture_output=True)
        logger.info("DNS cache cleared.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error clearing DNS: {e.stderr}")

def _disable_telemetry(logger: logging.Logger) -> List[str]:
    """Disable Windows telemetry services and tasks."""
    disabled = []
    # Services
    services = ['DiagTrack', 'dmwappushservice']
    for svc in services:
        try:
            subprocess.run(['sc', 'config', svc, 'start=', 'disabled'], check=True, capture_output=True)
            subprocess.run(['sc', 'stop', svc], check=True, capture_output=True)
            disabled.append(svc)
            logger.info(f"Disabled service: {svc}")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Error disabling service {svc}: {e.stderr}")
    
    # Tasks
    tasks = [r'\Microsoft\Windows\Customer Experience Improvement Program\Consolidator',
             r'\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser']
    for task in tasks:
        try:
            subprocess.run(['schtasks', '/change', '/tn', task, '/disable'], check=True, capture_output=True)
            disabled.append(task)
            logger.info(f"Disabled task: {task}")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Error disabling task {task}: {e.stderr}")
    
    return disabled

def _get_browser_paths(browser: str) -> List[Path]:
    """Get paths for browser data (cookies, cache, etc.)."""
    user_home = Path(os.path.expanduser('~'))
    if browser == 'chrome':
        return [user_home / 'AppData' / 'Local' / 'Google' / 'Chrome' / 'User Data' / 'Default' / 'Cookies',
                user_home / 'AppData' / 'Local' / 'Google' / 'Chrome' / 'User Data' / 'Default' / 'Cache']
    elif browser == 'firefox':
        profiles = user_home / 'AppData' / 'Roaming' / 'Mozilla' / 'Firefox' / 'Profiles'
        return [p / 'cookies.sqlite' for p in profiles.glob('*default*')] + [p / 'cache2' for p in profiles.glob('*default*')]
    elif browser == 'edge':
        return [user_home / 'AppData' / 'Local' / 'Microsoft' / 'Edge' / 'User Data' / 'Default' / 'Cookies',
                user_home / 'AppData' / 'Local' / 'Microsoft' / 'Edge' / 'User Data' / 'Default' / 'Cache']
    return []

def _clean_browser(browser: str, logger: logging.Logger) -> int:
    """Clean tracking data for a browser."""
    cleared = 0
    paths = _get_browser_paths(browser)
    for path in paths:
        if path.exists():
            try:
                if path.is_file():
                    os.remove(path)
                    cleared += 1
                elif path.is_dir():
                    shutil.rmtree(path)
                    cleared += len(list(path.rglob('*')))  # Approximate count
                logger.info(f"Cleared {browser} path: {path}")
            except PermissionError:
                logger.warning(f"Permission denied or in use: {path}. Close browser and retry.")
            except Exception as e:
                logger.error(f"Error cleaning {browser} path {path}: {str(e)}")
    return cleared