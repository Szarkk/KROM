"""
uninstall_residue.py

Enhancement module for Krom: Hunts for and removes leftovers from uninstalled apps,
such as orphaned registry keys and folders. Scans common paths and registry hives.

Associated with: After De-Bloat stage.
CLI Flags: --uninstall-residue (enable), --auto-remove (dangerous).

Exports: run_uninstall_residue(config: dict, logger: logging.Logger) -> None
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
try:
    import winreg  # For registry access on Windows
except ImportError:
    winreg = None
try:
    import psutil  # For process killing on locked files
except ImportError:
    psutil = None  # Will log warning if needed

# Stub import for backup (from utils/backup.py; implement if not present)
from ..utils.backup import create_backup, restore_backup  # Adjust path as per structure

def run_uninstall_residue(config: Dict[str, Any], logger: logging.Logger) -> None:
    """
    Run the uninstall residue remover enhancement.

    Args:
        config (Dict[str, Any]): Configuration dictionary.
        logger (logging.Logger): Logger instance for output.

    Returns:
        None
    """
    logger.info("=== Starting Uninstall Residue Remover ===")
    
    # Load config for uninstall_residue
    ur_config = config.get('enhancements', {}).get('uninstall_residue', {})
    enabled = ur_config.get('enabled', False)
    if not enabled:
        logger.info("Uninstall residue remover not enabled; skipping.")
        return
    
    # Early platform check: Windows-only for full features
    if platform.system() != 'Windows':
        logger.warning("Uninstall residue remover is designed for Windows (registry/WMI); limited on other platforms.")
    
    # Admin check
    is_admin = False
    if ctypes:
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception as e:
            logger.debug(f"Admin check failed: {e}")
    if not is_admin:
        logger.error("Uninstall residue remover requires administrator privileges. Run as admin. Skipping.")
        return
    
    scan_paths = [os.path.expandvars(p) for p in ur_config.get('scan_paths', [])]
    registry_hives = ur_config.get('registry_hives', [])
    keywords = ur_config.get('keywords', [])
    whitelist = ur_config.get('whitelist', ['Microsoft', 'Windows'])
    auto_remove = ur_config.get('auto_remove', False)
    report_only = ur_config.get('report_only', True)
    dry_run = config.get('dry_run', False)
    
    if report_only or dry_run:
        auto_remove = False  # Override for safety
    
    # Get installed apps for heuristics
    installed_apps = _get_installed_apps(logger)
    
    # Scan for residues
    file_residues = _scan_folders(scan_paths, keywords, whitelist, installed_apps, logger)
    reg_residues = _scan_registry(registry_hives, keywords, whitelist, installed_apps, logger) if platform.system() == 'Windows' and winreg else []
    
    all_residues = file_residues + reg_residues  # Combine; distinguish by type
    
    if not all_residues:
        logger.info("No uninstall residues found.")
        _generate_report([], config, logger)
        return
    
    logger.info(f"Found {len(all_residues)} potential residues.")
    
    # Backup if removal enabled
    backups_path = Path(config.get('paths', {}).get('backups', './backups')) / 'residue_backup'
    if not report_only and not dry_run:
        backups_path.mkdir(exist_ok=True)
        stage_name = 'uninstall_residue'
        backup_targets = [str(res) for res in file_residues] + [f"{r['hive']}\\{r['key']}" for r in reg_residues]
        create_backup(stage_name, config, logger, dry_run=False, targets=backup_targets)
    
    # Interactive review if not auto
    to_remove = all_residues if auto_remove else _interactive_review(all_residues, logger)
    
    # Remove selected
    removed = []
    for item in to_remove:
        if dry_run:
            logger.info(f"[Dry Run] Would remove: {item}")
        elif _safe_remove(item, logger, auto_remove, dry_run):
            removed.append(item)
    
    _generate_report(removed, config, logger)
    
    # Restore option stub (e.g., if needed post-run)
    if not report_only and not dry_run and input("Restore backups? (y/n): ").strip().lower() == 'y':
        restore_backup('uninstall_residue', config, logger, dry_run=False)
    
    logger.info("=== Uninstall Residue Remover Completed ===")

def _get_installed_apps(logger: logging.Logger) -> List[str]:
    """Get list of installed app names via WMI (Windows only)."""
    if platform.system() != 'Windows':
        return []
    try:
        result = subprocess.run(['wmic', 'product', 'get', 'name'], capture_output=True, text=True)
        apps = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return apps
    except Exception as e:
        logger.error(f"Failed to get installed apps: {e}")
        return []

def _scan_folders(paths: List[str], keywords: List[str], whitelist: List[str], installed_apps: List[str], logger: logging.Logger) -> List[Path]:
    """Scan folders for residues."""
    residues = []
    for path in paths:
        try:
            for entry in Path(path).iterdir():
                if entry.is_dir() or entry.is_file():
                    name = entry.name.lower()
                    if any(k.lower() in name for k in keywords) and not any(w.lower() in name for w in whitelist) and entry.name not in installed_apps:
                        residues.append(entry)
        except Exception as e:
            logger.error(f"Error scanning folder {path}: {str(e)}")
    return residues

def _scan_registry(hives: List[str], keywords: List[str], whitelist: List[str], installed_apps: List[str], logger: logging.Logger) -> List[Dict[str, str]]:
    """Scan registry for residues."""
    residues = []
    hive_map = {
        'HKLM': winreg.HKEY_LOCAL_MACHINE,
        'HKCU': winreg.HKEY_CURRENT_USER
    }
    for hive_str in hives:
        hive_parts = hive_str.split('\\', 1)
        hive_key = hive_map.get(hive_parts[0])
        subkey = hive_parts[1] if len(hive_parts) > 1 else ''
        if not hive_key:
            continue
        try:
            key = winreg.OpenKey(hive_key, subkey)
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    if any(k.lower() in subkey_name.lower() for k in keywords) and not any(w.lower() in subkey_name.lower() for w in whitelist) and subkey_name not in installed_apps:
                        residues.append({'hive': hive_parts[0], 'key': f"{subkey}\\{subkey_name}" if subkey else subkey_name})
                except OSError:
                    break
                i += 1
            winreg.CloseKey(key)
        except Exception as e:
            logger.error(f"Error scanning registry hive {hive_str}: {str(e)}")
    return residues

def _interactive_review(items: List, logger: logging.Logger) -> List:
    """Interactive CLI review for removal."""
    print("Potential Residues:")
    for i, item in enumerate(items, 1):
        if isinstance(item, Path):
            print(f"{i}. File/Folder: {item}")
        else:
            print(f"{i}. Registry: {item['hive']}\\{item['key']}")
    
    print("\nEnter numbers to remove (comma-separated, e.g., 1,3-5) or 'all' or 'none': ", end='')
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

def _safe_remove(item: Any, logger: logging.Logger, auto_remove: bool = False, dry_run: bool = False) -> bool:
    """
    Safely remove an item, handling locks and permissions.
    Kills locking processes if auto_remove, takes ownership, then deletes.
    """
    if dry_run:
        logger.info(f"[Dry Run] Would safely remove: {item}")
        return True
    
    try:
        if isinstance(item, Path):
            # Handle file/folder
            if psutil:
                # Find and kill locking processes
                for proc in psutil.process_iter(['pid', 'name', 'open_files']):
                    try:
                        if any(f.path.lower() == str(item).lower() for f in proc.info['open_files'] or []):
                            if auto_remove:
                                proc.kill()
                                logger.info(f"Killed locking process: {proc.info['name']} (PID: {proc.info['pid']})")
                            else:
                                logger.warning(f"Locking process found: {proc.info['name']} (PID: {proc.info['pid']}); skipping removal.")
                                return False
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            else:
                logger.warning("psutil not available; skipping process check.")
            
            # Take ownership (Windows-only)
            if platform.system() == 'Windows':
                try:
                    subprocess.run(['takeown', '/F', str(item), '/R', '/D', 'Y'], check=True, capture_output=True)
                    subprocess.run(['icacls', str(item), '/grant', 'Administrators:F', '/T'], check=True, capture_output=True)
                    logger.info(f"Took ownership of: {item}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to take ownership of {item}: {e}")
                    return False
            
            # Delete
            if item.is_dir():
                shutil.rmtree(item)
            else:
                os.remove(item)
            logger.info(f"Removed: {item}")
        else:
            # Registry (unchanged)
            hive_map = {'HKLM': winreg.HKEY_LOCAL_MACHINE, 'HKCU': winreg.HKEY_CURRENT_USER}
            hive = hive_map[item['hive']]
            winreg.DeleteKey(hive, item['key'])
            logger.info(f"Removed registry key: {item['key']}")
        return True
    except Exception as e:
        logger.error(f"Failed to remove {item}: {str(e)}")
        return False

def _generate_report(removed: List, config: Dict[str, Any], logger: logging.Logger) -> None:
    """Generate a report of removed residues."""
    logs_path = Path(config.get('paths', {}).get('logs', './logs'))
    report_path = logs_path / 'uninstall_residue_report.txt'
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("Krom Uninstall Residue Report\n")
        f.write("=" * 30 + "\n\n")
        f.write(f"Removed Items: {len(removed)}\n\n")
        for item in removed:
            if isinstance(item, Path):
                f.write(f"File/Folder: {item}\n")
            else:
                f.write(f"Registry: {item['hive']}\\{item['key']}\n")
    logger.info(f"Report saved to: {report_path}")