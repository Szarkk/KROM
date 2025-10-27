import os
import shutil
import winreg
import psutil
from pathlib import Path

def get_baseline_metrics(config, logger):
    """Capture pre-run baselines. Returns dict with metrics."""
    metrics = {}
    temp_dir = config.get('paths', {}).get('temp_dir', './temp')
    
    # Disk free (C:)
    try:
        metrics['disk_free_gb'] = shutil.disk_usage('C:\\').free / (1024 ** 3)
        logger.debug(f"Baseline disk free: {metrics['disk_free_gb']:.2f} GB")
    except:
        metrics['disk_free_gb'] = 0
    
    # Temp size
    try:
        temp_size = sum(os.path.getsize(p) for p in Path(temp_dir).rglob('*') if p.is_file()) / (1024 ** 3)  # GB, limit rglob if large
        metrics['temp_size_gb'] = temp_size
        logger.debug(f"Baseline temp size: {temp_size:.2f} GB")
    except:
        metrics['temp_size_gb'] = 0
    
    # Startup items (simple reg count)
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run')
        count = winreg.QueryInfoKey(key)[0]  # Value count
        winreg.CloseKey(key)
        metrics['startup_items'] = count
        logger.debug(f"Baseline startup items: {count}")
    except:
        metrics['startup_items'] = 0
    
    return metrics

def get_current_metrics(config, logger):
    """Re-capture post-run metrics (same as baseline)."""
    return get_baseline_metrics(config, logger)  # Reuse for simplicity