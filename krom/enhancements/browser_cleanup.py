"""
browser_cleanup.py

Enhancement module for Krom: Cleans browser-specific junk like caches, history, cookies,
downloads, and extensions (with whitelist). Targets major browsers including Opera.

Associated with: Temp Clean stage.
CLI Flags: --browser-cleanup (enable), --browsers <chrome,firefox,edge,opera>.

Exports: run_browser_cleanup(config: dict, logger: logging.Logger) -> None
"""

import logging
import os
import platform
import shutil
import psutil
from pathlib import Path
from typing import Dict, Any, List

def run_browser_cleanup(config: Dict[str, Any], logger: logging.Logger) -> None:
    """
    Run the browser cleanup enhancement.

    Args:
        config (Dict[str, Any]): Configuration dictionary.
        logger (logging.Logger): Logger instance for output.

    Returns:
        None
    """
    logger.info("=== Starting Browser Cleanup ===")
    
    # Load config for browser_cleanup
    bc_config = config.get('enhancements', {}).get('browser_cleanup', {})
    enabled = bc_config.get('enabled', False)
    if not enabled:
        logger.info("Browser cleanup not enabled; skipping.")
        return
    
    browsers = bc_config.get('browsers', ['chrome', 'firefox', 'edge', 'opera'])
    clean_types = bc_config.get('clean_types', ['cache', 'history', 'cookies', 'downloads', 'extensions'])
    safe_extensions = bc_config.get('safe_extensions', [])
    backup_enabled = bc_config.get('backup', True) and not config.get('no_backup', False)
    dry_run = config.get('dry_run', False)
    
    # Platform-specific path adjustments (focus on Windows; stubs for others)
    if platform.system() != 'Windows':
        logger.warning("Browser cleanup optimized for Windows; paths may vary on other platforms.")
    
    user_home = Path(os.path.expanduser('~'))
    
    # Check for running browsers
    running_browsers = []
    for browser in browsers:
        if _is_browser_running(browser):
            running_browsers.append(browser)
    if running_browsers:
        logger.warning(f"Running browsers detected: {', '.join(running_browsers)}. Close them for full cleanup or proceed with skips.")
        # Optional: Prompt to continue? For now, proceed with potential skips.
    
    # Backup if enabled
    backups_path = Path(config.get('paths', {}).get('backups', './backups'))
    if backup_enabled and not dry_run:
        backups_path.mkdir(exist_ok=True)
        for browser in browsers:
            paths = _get_browser_paths(browser, user_home)
            for path in paths:
                if path.exists():
                    backup_dest = backups_path / f'browser_{browser}_backup' / path.relative_to(user_home)
                    backup_dest.parent.mkdir(exist_ok=True)
                    if path.is_dir():
                        shutil.copytree(path, backup_dest, dirs_exist_ok=True)
                    else:
                        shutil.copy(path, backup_dest)
                    logger.info(f"Backed up {browser} path: {path}")
    
    # Dry-run simulation
    if dry_run:
        logger.info("Dry-run mode: Simulating browser cleanup without changes.")
        for browser in browsers:
            paths = _get_browser_paths(browser, user_home)
            for path in paths:
                if path.exists():
                    logger.info(f"Would clean {browser} path: {path}")
        logger.info("=== Browser Cleanup Simulated (Dry-Run) ===")
        return
    
    # Perform cleanup
    freed_space = 0
    for browser in browsers:
        before_space = _get_dir_size(user_home) if 'downloads' in clean_types else 0  # Approximate; or use psutil.disk_usage
        cleared = _clean_browser(browser, clean_types, safe_extensions, user_home, logger)
        after_space = _get_dir_size(user_home) if 'downloads' in clean_types else 0
        freed = before_space - after_space
        freed_space += freed
        logger.info(f"Cleared {cleared} items for {browser}; approx. freed {freed / (1024 * 1024):.2f} MB.")
    
    logger.info(f"Total approx. freed space: {freed_space / (1024 * 1024):.2f} MB.")
    logger.info("=== Browser Cleanup Completed ===")

def _get_browser_paths(browser: str, user_home: Path) -> List[Path]:
    """Get paths for browser junk based on clean_types (all by default)."""
    # Note: clean_types filtered later; return all potential paths
    if browser == 'chrome':
        base = user_home / 'AppData' / 'Local' / 'Google' / 'Chrome' / 'User Data' / 'Default'
        return [
            base / 'Cache',  # cache
            base / 'History',  # history
            base / 'Cookies',  # cookies
            user_home / 'Downloads',  # downloads (shared)
            base / 'Extensions'  # extensions
        ]
    elif browser == 'firefox':
        profiles = user_home / 'AppData' / 'Roaming' / 'Mozilla' / 'Firefox' / 'Profiles'
        paths = []
        for profile in profiles.glob('*default*'):
            paths.extend([
                profile / 'cache2',  # cache
                profile / 'places.sqlite',  # history
                profile / 'cookies.sqlite',  # cookies
                user_home / 'Downloads',  # downloads
                profile / 'extensions'  # extensions
            ])
        return paths
    elif browser == 'edge':
        base = user_home / 'AppData' / 'Local' / 'Microsoft' / 'Edge' / 'User Data' / 'Default'
        return [
            base / 'Cache',  # cache
            base / 'History',  # history
            base / 'Cookies',  # cookies
            user_home / 'Downloads',  # downloads
            base / 'Extensions'  # extensions
        ]
    elif browser == 'opera':
        roam_base = user_home / 'AppData' / 'Roaming' / 'Opera Software' / 'Opera Stable'
        local_base = user_home / 'AppData' / 'Local' / 'Opera Software' / 'Opera Stable'
        return [
            local_base / 'Cache',  # cache
            roam_base / 'History',  # history
            roam_base / 'Cookies',  # cookies (or Network/Cookies)
            user_home / 'Downloads',  # downloads
            roam_base / 'Extensions'  # extensions
        ]
    else:
        return []

def _is_browser_running(browser: str) -> bool:
    """Check if browser is running."""
    exe_map = {
        'chrome': 'chrome.exe',
        'firefox': 'firefox.exe',
        'edge': 'msedge.exe',
        'opera': 'opera.exe'
    }
    exe = exe_map.get(browser)
    if exe:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == exe:
                return True
    return False

def _clean_browser(browser: str, clean_types: List[str], safe_extensions: List[str], user_home: Path, logger: logging.Logger) -> int:
    """Clean specified types for a browser."""
    cleared = 0
    all_paths = _get_browser_paths(browser, user_home)
    for path in all_paths:
        type_map = {
            'Cache': 'cache',
            'History': 'history',
            'Cookies': 'cookies',
            'Downloads': 'downloads',
            'Extensions': 'extensions'
        }
        path_name = path.name
        clean_type = type_map.get(path_name, '')
        if clean_type not in clean_types:
            continue
        
        if path.exists():
            try:
                if clean_type == 'extensions':
                    # Handle extensions with whitelist
                    if path.is_dir():
                        for ext_dir in path.iterdir():
                            if ext_dir.name not in safe_extensions:
                                shutil.rmtree(ext_dir)
                                cleared += 1
                                logger.info(f"Removed extension: {ext_dir}")
                elif path.is_dir():
                    shutil.rmtree(path)
                    cleared += 1
                    logger.info(f"Cleared {browser} {clean_type}: {path}")
                else:
                    os.remove(path)
                    cleared += 1
                    logger.info(f"Cleared {browser} {clean_type}: {path}")
            except PermissionError:
                logger.warning(f"Permission denied or in use: {path}. Close browser and retry.")
            except Exception as e:
                logger.error(f"Error cleaning {browser} path {path}: {str(e)}")
    return cleared

def _get_dir_size(path: Path) -> int:
    """Calculate approximate size of a directory in bytes."""
    total = 0
    if path.exists():
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = Path(dirpath) / f
                total += fp.stat().st_size if not fp.is_symlink() else 0
    return total