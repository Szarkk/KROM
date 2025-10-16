import os
import sys
import copy
import logging
from typing import Any, Dict

import yaml

def resource_path(relative_path: str) -> str:
    """
    Get the absolute path to a bundled resource, handling both dev and PyInstaller frozen modes.
    """
    if getattr(sys, 'frozen', False):  # Running as PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Project root
    return os.path.join(base_path, relative_path)

def get_app_dir() -> str:
    """
    Get the directory containing the executable (frozen mode) or project root (dev mode).
    This is used for output paths like logs and backups.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def resolve_paths(config: Dict) -> Dict:
    """
    Resolve relative paths in config['paths'] to absolute paths based on the app dir.
    Leaves absolute paths unchanged.
    """
    app_dir = get_app_dir()
    if 'paths' in config:
        for key, val in config['paths'].items():
            if not os.path.isabs(val):
                config['paths'][key] = os.path.abspath(os.path.join(app_dir, val))
    return config

def load_config(config_path: str = 'configs/default.yaml') -> Dict:
    """
    Load the configuration from the specified YAML file, merging with defaults.
    Handles path resolution for both script and bundled (PyInstaller) modes.
    If the file is not found, returns the default configuration.
    Resolves output paths to be relative to the app dir.
    """
    full_path = resource_path(config_path)
    
    defaults = get_default_config()
    
    try:
        with open(full_path, 'r') as f:
            user_config = yaml.safe_load(f)
        if not isinstance(user_config, dict):
            logging.warning(f"Invalid config format in {full_path}. Using defaults.")
            return resolve_paths(defaults)
        merged = merge_configs(defaults, user_config)
        return resolve_paths(merged)
    except FileNotFoundError:
        logging.warning(f"Config file {full_path} not found. Using defaults.")
        return resolve_paths(defaults)
    except yaml.YAMLError as e:
        logging.warning(f"Error parsing config {full_path}: {e}. Using defaults.")
        return resolve_paths(defaults)

def get_config_value(config: Dict, key: str, default: Any = None, category: str = None) -> Any:
    """
    Safely retrieve a value from the config dict, supporting nested keys via dot notation.
    If category is provided, scopes the lookup to config[category].
    Handles cases where values are booleans or dicts with 'enabled' key.
    """
    if category:
        section = config.get(category, {})
    else:
        section = config
    
    if '.' in key:
        keys = key.split('.')
        for k in keys[:-1]:
            section = section.get(k, {})
            if not isinstance(section, dict):
                return default
        val = section.get(keys[-1], default)
    else:
        val = section.get(key, default)
    
    if isinstance(val, dict):
        return val.get('enabled', default)
    return val

def merge_configs(base: Dict, overrides: Dict) -> Dict:
    """
    Recursively merge two dictionaries, with overrides taking precedence.
    Returns a new dict without modifying the inputs.
    """
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result

def get_default_config() -> Dict:
    """
    Return the hardcoded default configuration, mirroring the structure in default.yaml.
    """
    return {
        'paths': {
            'backups': "./backups",
            'logs': "./logs",
            'temp_dir': "./temp"
        },
        'stages': {
            'prep': {'enabled': True},
            'temp_clean': {'enabled': True},
            'de_bloat': {'enabled': True},
            'disinfect': {
                'enabled': True,
                'av_tools': [
                    {
                        'name': 'ClamAV',
                        'download_url': "https://www.clamav.net/downloads/production/clamav-1.4.3.win.x64.exe",
                        'install_cmd': "--mode unattended --install-location C:\\ClamAV",
                        'update_cmd': "C:\\ClamAV\\freshclam.exe",
                        'scan_cmd': "C:\\ClamAV\\clamscan.exe -r C:\\ --bell -i --remove",
                        'uninstall_cmd': "C:\\ClamAV\\uninstall.exe /S",
                        'detect_cmd': "dir C:\\ClamAV /b >nul 2>&1 && echo installed",
                        'keep_installed': False
                    },
                    {
                        'name': 'Malwarebytes',
                        'download_url': "https://downloads.malwarebytes.com/file/mwb-download/mwb-free-latest.exe",
                        'install_cmd': "/VERYSILENT /NORESTART /SUPPRESSMSGBOXES",
                        'update_cmd': '"C:\\Program Files\\Malwarebytes\\Anti-Malware\\mbam.exe" /update',
                        'scan_cmd': '"C:\\Program Files\\Malwarebytes\\Anti-Malware\\mbam.exe" /scan -full -terminate',
                        'uninstall_cmd': '"C:\\Program Files\\Malwarebytes\\Anti-Malware\\unins000.exe" /VERYSILENT /NORESTART',
                        'detect_cmd': "wmic product get name | findstr Malwarebytes",
                        'keep_installed': False
                    }
                ],
                'max_concurrent': 1,
                'temp_dir': "./temp_av_downloads",
                'keep_installed': False,
                'auto_update': True
            },
            'repair': {'enabled': True},
            'patch': {'enabled': True},
            'optimize': {'enabled': True},
            'wrap_up': {'enabled': True},
            'custom': {'enabled': False}
        },
        'enhancements': {
            'browser_cleanup': {
                'enabled': False,
                'browsers': ['chrome', 'firefox', 'edge', 'opera'],
                'clean_types': ['cache', 'history', 'cookies', 'downloads', 'extensions'],
                'safe_extensions': [],
                'backup': True
            },
            'privacy_scrub': {
                'enabled': False,
                'hosts_blocks': [],
                'browsers': ['chrome', 'firefox', 'edge', 'opera'],
                'clear_dns': True,
                'disable_telemetry': True,
                'hosts_file': "C:\\Windows\\System32\\drivers\\etc\\hosts",
                'online_update': False
            },
            'uninstall_residue': {
                'enabled': False,
                'scan_paths': [
                    "C:\\Program Files",
                    "C:\\Program Files (x86)",
                    "%APPDATA%",
                    "%LOCALAPPDATA%"
                ],
                'registry_hives': [
                    "HKLM\\SOFTWARE",
                    "HKCU\\SOFTWARE",
                    "HKLM\\SOFTWARE\\WOW6432Node"
                ],
                'keywords': [],
                'whitelist': ['Microsoft', 'Windows'],
                'auto_remove': False,
                'report_only': True
            },
            'driver_audit': {
                'enabled': False,
                'keywords': [
                    'display', 'video', 'graphics', 'network', 'ethernet', 'wifi', 'adapter'
                ],
                'suggestions': {
                    'NVIDIA': "https://www.nvidia.com/Download/index.aspx",
                    'AMD': "https://www.amd.com/en/support",
                    'INTEL': "https://www.intel.com/content/www/us/en/support/detect.html",
                    'REALTEK': "https://www.realtek.com/en/downloads",
                    'BROADCOM': "https://www.broadcom.com/support/download-search",
                    'QUALCOMM': "https://www.qualcomm.com/support",
                    'MICROSOFT': "Use Windows Update for built-in drivers."
                }
            },
            'startup_manager': {
                'enabled': False,
                'interactive': True,
                'blacklist': [],
                'whitelist': [],
                'include_services': True,
                'include_tasks': True,
                'include_registry': True
            },
            'benchmark_report': {
                'enabled': False,
                'metrics': ['cpu', 'memory', 'disk', 'network'],
                'visualize': True,
                'pre_post': True,
                'report_path': "./logs/benchmark_report.txt"
            },
            'scheduled_mode': {
                'enabled': False,
                'frequency': "weekly",
                'task_name': "KromScheduledClean",
                'args': [],
                'interactive': True
            },
            'hardware_health': {'enabled': False},
            'secure_wipe': {
                'enabled': False,
                'method': "dod",
                'passes': 3,
                'wipe_paths': [],
                'no_confirm': False
            }
        },
        'verbose': False,
        'dry_run': False,
        'no_backup': False,
        'safe_mode': False
    }