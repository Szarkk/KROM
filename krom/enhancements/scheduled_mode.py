"""
scheduled_mode.py

Enhancement module for Krom: Sets up scheduled runs of Krom using OS-native schedulers
(e.g., Task Scheduler on Windows, cron on Linux). Prompts interactively or auto-configures.

Associated with: Post-Run Option (Wrap-Up stage).
CLI Flags: --scheduled-mode (enable), --frequency <weekly/daily/monthly>.

Exports: run_scheduled_mode(config: dict, logger: logging.Logger) -> None
"""

import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

try:
    import ctypes  # For admin check on Windows
except ImportError:
    ctypes = None

def run_scheduled_mode(config: Dict[str, Any], logger: logging.Logger) -> None:
    """
    Run the scheduled mode enhancement.

    Args:
        config (Dict[str, Any]): Configuration dictionary.
        logger (logging.Logger): Logger instance for output.

    Returns:
        None
    """
    logger.info("=== Starting Scheduled Mode ===")
    
    # Load config for scheduled_mode
    sm_config = config.get('enhancements', {}).get('scheduled_mode', {})
    enabled = sm_config.get('enabled', False)
    if not enabled:
        logger.info("Scheduled mode not enabled; skipping.")
        return
    
    frequency = sm_config.get('frequency', 'weekly').lower()
    task_name = sm_config.get('task_name', 'KromScheduledClean')
    args = sm_config.get('args', [])
    interactive = sm_config.get('interactive', True)
    dry_run = config.get('dry_run', False)
    
    # Get Krom path (assume exe or py; adjust if needed)
    krom_path = Path(sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]).absolute()
    cmd = f'"{krom_path}" {" ".join(args)}'
    
    # Validate frequency
    valid_frequencies = ['daily', 'weekly', 'monthly']
    if frequency not in valid_frequencies:
        logger.error(f"Invalid frequency '{frequency}'; must be one of {valid_frequencies}. Skipping.")
        return
    
    # Admin check (required for schtasks/cron)
    is_admin = False
    if platform.system() == 'Windows' and ctypes:
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception as e:
            logger.debug(f"Admin check failed: {e}")
    elif platform.system() in ['Linux', 'Darwin']:
        is_admin = os.geteuid() == 0  # Root check
    if not is_admin:
        logger.error("Scheduled mode requires administrator/root privileges. Run as admin/sudo. Skipping.")
        return
    
    # Interactive prompt if enabled
    if interactive:
        print("Do you want to schedule recurring Krom runs? (y/n): ", end='', file=sys.stderr)
        response = input().strip().lower()
        if not response.startswith('y'):
            logger.info("User declined scheduling.")
            return
        print("Choose frequency: 1=daily, 2=weekly (default), 3=monthly: ", end='', file=sys.stderr)
        freq_choice = input().strip() or '2'
        frequency = ['daily', 'weekly', 'monthly'][int(freq_choice) - 1]
    
    # Dry-run simulation
    if dry_run:
        logger.info("Dry-run mode: Simulating scheduling without creation.")
        logger.info(f"Would schedule '{task_name}' to run {frequency} with command: {cmd}")
        logger.info("=== Scheduled Mode Simulated (Dry-Run) ===")
        return
    
    # Platform-specific scheduling
    success = False
    os_system = platform.system()
    if os_system == 'Windows':
        success = _schedule_windows(frequency, task_name, cmd, logger)
    elif os_system == 'Linux':
        success = _schedule_linux(frequency, task_name, cmd, logger)
    elif os_system == 'Darwin':  # macOS
        success = _schedule_mac(frequency, task_name, cmd, logger)
    else:
        logger.error(f"Unsupported platform: {os_system}. Skipping.")
        return
    
    if success:
        logger.info(f"Scheduled '{task_name}' to run {frequency}.")
        logger.info(f"To remove: On Windows: schtasks /delete /tn {task_name} /f")
        logger.info("On Linux: crontab -e and remove the line")
        logger.info("On macOS: launchctl unload ~/Library/LaunchAgents/com.krom.clean.plist")
    else:
        logger.error("Scheduling failed. Check logs for details.")
    
    logger.info("=== Scheduled Mode Completed ===")

def _schedule_windows(frequency: str, task_name: str, cmd: str, logger: logging.Logger) -> bool:
    """Schedule on Windows using schtasks."""
    freq_map = {
        'daily': '/sc DAILY /st 02:00',
        'weekly': '/sc WEEKLY /d MON /st 02:00',
        'monthly': '/sc MONTHLY /d 1 /st 02:00'
    }
    sch_cmd = ['schtasks', '/create', '/tn', task_name, '/tr', cmd, '/f', '/rl', 'HIGHEST'] + freq_map[frequency].split()
    try:
        # Check if exists
        query = subprocess.run(['schtasks', '/query', '/tn', task_name], capture_output=True, text=True)
        if query.returncode == 0:
            logger.warning(f"Task '{task_name}' exists. Overwriting.")
        
        result = subprocess.run(sch_cmd, check=True, capture_output=True, text=True)
        logger.debug(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error scheduling on Windows: {e.stderr}")
        return False

def _schedule_linux(frequency: str, task_name: str, cmd: str, logger: logging.Logger) -> bool:
    """Schedule on Linux using cron."""
    cron_map = {
        'daily': '0 2 * * *',
        'weekly': '0 2 * * 1',  # Monday
        'monthly': '0 2 1 * *'
    }
    cron_entry = f"{cron_map[frequency]} {cmd} # {task_name}\n"
    try:
        # Get current crontab
        current = subprocess.run(['crontab', '-l'], capture_output=True, text=True).stdout
        if f"# {task_name}" in current:
            logger.warning(f"Cron entry for '{task_name}' exists. Updating.")
            current = '\n'.join(line for line in current.splitlines() if f"# {task_name}" not in line) + '\n'
        
        new_cron = current + cron_entry
        subprocess.run(['crontab', '-'], input=new_cron, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error scheduling on Linux: {e.stderr}")
        return False

def _schedule_mac(frequency: str, task_name: str, cmd: str, logger: logging.Logger) -> bool:
    """Schedule on macOS using launchd."""
    plist_path = Path(os.path.expanduser('~')) / 'Library' / 'LaunchAgents' / 'com.krom.clean.plist'
    freq_map = {
        'daily': '<key>StartCalendarInterval</key><dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>0</integer></dict>',
        'weekly': '<key>StartCalendarInterval</key><dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>0</integer><key>Weekday</key><integer>1</integer></dict>',  # Monday
        'monthly': '<key>StartCalendarInterval</key><dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>0</integer><key>Day</key><integer>1</integer></dict>'
    }
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.krom.clean</string>
    <key>ProgramArguments</key>
    <array>
        <string>{cmd.split()[0]}</string>
        {"".join(f"<string>{arg}</string>" for arg in cmd.split()[1:])}
    </array>
    {freq_map[frequency]}
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""
    try:
        if plist_path.exists():
            logger.warning(f"Launchd plist exists. Overwriting.")
            subprocess.run(['launchctl', 'unload', str(plist_path)], capture_output=True)
        
        with open(plist_path, 'w') as f:
            f.write(plist_content)
        
        subprocess.run(['launchctl', 'load', str(plist_path)], check=True)
        return True
    except Exception as e:
        logger.error(f"Error scheduling on macOS: {str(e)}")
        return False