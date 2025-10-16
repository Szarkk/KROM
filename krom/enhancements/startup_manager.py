"""
startup_manager.py

Enhancement module for Krom: Audits and manages startup items (registry, services, tasks)
to optimize boot times. Supports interactive review or auto-disable based on blacklist.

Associated with: During Optimize stage.
CLI Flags: --startup-manager (enable), --interactive / --no-interactive,
           --blacklist <item1,item2> (comma-separated).

Exports: run_startup_manager(config: dict, logger: logging.Logger) -> None
"""

import logging
import platform
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List
try:
    import ctypes  # For admin check on Windows
except ImportError:
    ctypes = None
try:
    import winreg  # For registry access on Windows
except ImportError:
    winreg = None
import psutil  # For boot time measurement

def run_startup_manager(config: Dict[str, Any], logger: logging.Logger) -> None:
    """
    Run the startup manager enhancement.

    Args:
        config (Dict[str, Any]): Configuration dictionary.
        logger (logging.Logger): Logger instance for output.

    Returns:
        None
    """
    logger.info("=== Starting Startup Manager ===")
    
    # Load config for startup_manager
    sm_config = config.get('enhancements', {}).get('startup_manager', {})
    enabled = sm_config.get('enabled', False)
    if not enabled:
        logger.info("Startup manager not enabled; skipping.")
        return
    
    # Early platform check: Windows-only for now
    if platform.system() != 'Windows':
        logger.warning("Startup manager is designed for Windows; skipping on current platform.")
        return
    
    # Admin check
    is_admin = False
    if ctypes:
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception as e:
            logger.debug(f"Admin check failed: {e}")
    if not is_admin:
        logger.error("Startup manager requires administrator privileges. Run Krom as admin. Skipping.")
        return
    
    interactive = sm_config.get('interactive', True)
    blacklist = sm_config.get('blacklist', [])
    whitelist = sm_config.get('whitelist', [])
    include_services = sm_config.get('include_services', True)
    include_tasks = sm_config.get('include_tasks', True)
    include_registry = sm_config.get('include_registry', True)
    dry_run = config.get('dry_run', False)
    
    # Backup registry if including registry
    if include_registry and not dry_run:
        backup_path = Path(config.get('paths', {}).get('backups', './backups')) / 'startup_reg_backup.reg'
        backup_path.parent.mkdir(exist_ok=True)
        try:
            subprocess.run(['reg', 'export', r'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run', str(backup_path), '/y'], check=True)
            subprocess.run(['reg', 'export', r'HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run', str(backup_path), '/y'], check=True)
            logger.info(f"Registry backups created at: {backup_path}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to backup registry: {e.stderr}")
    
    # Gather startup items
    items: List[Dict[str, Any]] = []
    if include_registry:
        items.extend(_get_registry_startups(logger))
    if include_services:
        items.extend(_get_services(logger))
    if include_tasks:
        items.extend(_get_tasks(logger))
    
    if not items:
        logger.warning("No startup items found. Skipping.")
        return
    
    logger.info(f"Found {len(items)} startup items.")
    
    # Filter whitelist
    filtered_items = [item for item in items if not any(w.lower() in item['name'].lower() for w in whitelist)]
    
    # Dry-run simulation
    if dry_run:
        logger.info("Dry-run mode: Listing startup items without changes.")
        for i, item in enumerate(filtered_items, 1):
            logger.info(f"{i}. {item['name']} ({item['type']}) - Path: {item.get('path', 'N/A')} - Enabled: {item['enabled']}")
        logger.info("=== Startup Manager Simulated (Dry-Run) ===")
        return
    
    # Process items
    to_disable = []
    if interactive:
        to_disable = _interactive_menu(filtered_items, logger)
    else:
        to_disable = [item for item in filtered_items if any(b.lower() in item['name'].lower() or b.lower() in item.get('path', '').lower() for b in blacklist)]
        if not blacklist:
            logger.warning("Non-interactive mode with empty blacklist; no auto-disables.")
    
    # Apply disables
    disabled_count = 0
    for item in to_disable:
        if _disable_item(item, logger):
            disabled_count += 1
    
    logger.info(f"Startup manager completed: {disabled_count} items disabled.")
    
    # Optional: Measure boot time impact (stub; requires reboot)
    if config.get('enhancements', {}).get('benchmark_report', {}).get('enabled', False):
        logger.info(f"Current boot time: {psutil.boot_time()} seconds since last boot. Reboot to measure impact.")
    
    logger.info("=== Startup Manager Completed ===")

def _get_registry_startups(logger: logging.Logger) -> List[Dict[str, Any]]:
    """Get startup items from registry."""
    items = []
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run'),
        (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run'),
        (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce'),
        (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce')
    ]
    for hkey, subkey in keys:
        try:
            key = winreg.OpenKey(hkey, subkey)
            i = 0
            while True:
                name, path, _ = winreg.EnumValue(key, i)
                items.append({'type': 'registry', 'name': name, 'path': path, 'enabled': True, 'key_path': (hkey, subkey)})
                i += 1
        except OSError:
            pass  # End of values
        except Exception as e:
            logger.error(f"Error reading registry: {e}")
    return items

def _get_services(logger: logging.Logger) -> List[Dict[str, Any]]:
    """Get auto-start services."""
    items = []
    try:
        result = subprocess.run(['wmic', 'service', 'where', "StartMode='Auto'", 'get', 'Name,PathName,State', '/format:list'], capture_output=True, text=True, check=True)
        output = result.stdout.strip().split('\n\n')
        for block in output:
            if block:
                lines = block.split('\n')
                name = lines[0].split('=')[1].strip() if lines[0].startswith('Name=') else ''
                path = lines[1].split('=')[1].strip() if len(lines) > 1 and lines[1].startswith('PathName=') else ''
                state = lines[2].split('=')[1].strip() if len(lines) > 2 and lines[2].startswith('State=') else ''
                if name and state == 'Running':
                    items.append({'type': 'service', 'name': name, 'path': path, 'enabled': True})
    except subprocess.CalledProcessError as e:
        logger.error(f"Error querying services: {e.stderr}")
    return items

def _get_tasks(logger: logging.Logger) -> List[Dict[str, Any]]:
    """Get scheduled tasks with boot/login triggers."""
    items = []
    try:
        result = subprocess.run(['schtasks', '/query', '/fo', 'LIST', '/v'], capture_output=True, text=True, check=True)
        output = result.stdout.strip().split('\n\n')
        for block in output:
            if block:
                lines = {line.split(':', 1)[0].strip(): line.split(':', 1)[1].strip() for line in block.split('\n') if ':' in line}
                name = lines.get('TaskName', '')
                status = lines.get('Status', '')
                if name and status == 'Ready' and ('At log on' in lines.get('Triggers', '') or 'At system start up' in lines.get('Triggers', '')):
                    items.append({'type': 'task', 'name': name, 'path': lines.get('Task To Run', ''), 'enabled': True})
    except subprocess.CalledProcessError as e:
        logger.error(f"Error querying tasks: {e.stderr}")
    return items

def _interactive_menu(items: List[Dict[str, Any]], logger: logging.Logger) -> List[Dict[str, Any]]:
    """Interactive CLI menu for selecting items to disable."""
    print("Startup Items:")
    for i, item in enumerate(items, 1):
        print(f"{i}. {item['name']} ({item['type']}) - Path: {item.get('path', 'N/A')} - Enabled: {item['enabled']}")
    
    print("\nEnter numbers to disable (comma-separated, e.g., 1,3-5) or 'all' or 'none': ", end='')
    response = input().strip().lower()
    if response == 'none':
        return []
    elif response == 'all':
        return items
    
    selected = []
    try:
        for part in response.split(','):
            if '-' in part:
                start, end = map(int, part.split('-'))
                selected.extend(items[j-1] for j in range(start, end+1))
            else:
                selected.append(items[int(part)-1])
    except (ValueError, IndexError):
        logger.warning("Invalid input; no items selected.")
    return selected

def _disable_item(item: Dict[str, Any], logger: logging.Logger) -> bool:
    """Disable a startup item based on type."""
    try:
        if item['type'] == 'registry':
            hkey, subkey = item['key_path']
            key = winreg.OpenKey(hkey, subkey, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, item['name'])
            winreg.CloseKey(key)
            logger.info(f"Disabled registry item: {item['name']}")
        elif item['type'] == 'service':
            subprocess.run(['sc', 'config', item['name'], 'start=', 'demand'], check=True)
            logger.info(f"Disabled service: {item['name']}")
        elif item['type'] == 'task':
            subprocess.run(['schtasks', '/change', '/tn', item['name'], '/disable'], check=True)
            logger.info(f"Disabled task: {item['name']}")
        return True
    except Exception as e:
        logger.error(f"Failed to disable {item['name']} ({item['type']}): {str(e)}")
        return False