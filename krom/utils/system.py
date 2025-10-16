import logging
import subprocess
import platform
import ctypes
import sys
import os

def run_system_command(cmd: list, logger: logging.Logger, dry_run: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    if dry_run:
        logger.info(f"[Dry Run] Would run command: {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, "", "")  # Mock success
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        logger.debug(f"Command {' '.join(cmd)} output: {result.stdout}")
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Command {' '.join(cmd)} failed: {e.stderr}")
        raise

def is_windows() -> bool:
    return platform.system() == 'Windows'

def is_admin() -> bool:
    """
    Check if the current process is running with administrator privileges.
    Returns True if admin (Windows only), False otherwise.
    """
    if not is_windows():
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def run_as_admin(logger: logging.Logger, args=None):
    """
    Check if running as admin; if not, relaunch the script with elevated privileges.
    Respects dry_run (simulates relaunch) and verbose (logs details).
    If relaunch fails, logs error and exits.
    
    Args:
        logger: Logger instance for output.
        args: Optional argparse.Namespace for dry_run/verbose flags (fallback to False).
    """
    dry_run = getattr(args, 'dry_run', False) if args else False
    verbose = getattr(args, 'verbose', False) if args else False
    
    if is_admin():
        if verbose:
            logger.info("Already running with admin privileges.")
        return  # No action needed
    
    if dry_run:
        logger.info("[Dry Run] Would relaunch as admin.")
        return  # Simulate
    
    logger.warning("Not running as admin; attempting to relaunch with elevated privileges.")
    
    try:
        # Get current script path and args
        exe = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
        params = ' '.join(sys.argv[1:])  # Preserve original args
        
        # Use ShellExecuteW to elevate (triggers UAC prompt)
        res = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, os.getcwd(), 1  # 1 = SW_SHOWNORMAL
        )
        
        if res <= 32:  # Error codes <=32 indicate failure
            raise RuntimeError(f"ShellExecuteW failed with code {res}")
        
        sys.exit(0)  # Exit current process after relaunch
    except Exception as e:
        logger.error(f"Failed to relaunch as admin: {e}")
        sys.exit(1)  # Exit with error