"""
secure_wipe.py

Enhancement module for Krom: Securely wipes specified files or folders using multi-pass overwrites
to prevent data recovery. Supports methods like DoD (3-pass), simple (1-pass random), and Gutmann (35-pass).

Associated with: Pre-Run or Standalone.
CLI Flags: --secure-wipe (enable), --wipe-paths <path1,path2>, --wipe-method <dod/simple/gutmann>,
           --wipe-passes <n> (for custom), --no-confirm (skip prompt; dangerous).

Exports: run_secure_wipe(config: dict, logger: logging.Logger) -> None
"""

import logging
import os
import platform
import secrets
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB chunks for large files

def run_secure_wipe(config: Dict[str, Any], logger: logging.Logger) -> None:
    """
    Run the secure wipe enhancement.

    Args:
        config (Dict[str, Any]): Configuration dictionary (e.g., {'enhancements': {'secure_wipe': {...}}}).
        logger (logging.Logger): Logger instance for output.

    Returns:
        None
    """
    logger.info("=== Starting Secure Wipe ===")
    
    # Load config for secure_wipe
    wipe_config = config.get('enhancements', {}).get('secure_wipe', {})
    enabled = wipe_config.get('enabled', False)
    if not enabled:
        logger.info("Secure wipe not enabled; skipping.")
        return
    
    wipe_paths = wipe_config.get('wipe_paths', [])
    if not wipe_paths:
        logger.error("No wipe_paths specified in config. Skipping secure wipe to avoid accidents.")
        return
    
    method = wipe_config.get('method', 'dod').lower()
    passes = wipe_config.get('passes', 3)  # For custom
    no_confirm = wipe_config.get('no_confirm', False)
    dry_run = config.get('dry_run', False)
    
    # Expand and resolve paths
    resolved_paths: List[Path] = []
    for p in wipe_paths:
        expanded = os.path.expanduser(p)
        abs_path = Path(expanded).resolve()
        if abs_path.exists():
            resolved_paths.append(abs_path)
        else:
            logger.warning(f"Path does not exist: {abs_path}. Skipping.")
    
    if not resolved_paths:
        logger.error("No valid paths to wipe. Aborting.")
        return
    
    # Platform warning if not Windows (but proceed, as logic is cross-platform)
    if platform.system() != 'Windows':
        logger.warning("Secure wipe is optimized for Windows; behavior may vary on other platforms.")
    
    # SSD detection and warning (Windows-specific; optional, requires subprocess)
    if platform.system() == 'Windows':
        try:
            import subprocess
            cmd = ['wmic', 'diskdrive', 'get', 'MediaType,Index', '/format:list']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.lower()
            if 'solid state device' in output:
                logger.warning("SSD detected. Secure wipe may not fully prevent recovery due to wear-leveling/TRIM. Consider full-disk encryption instead.")
        except Exception as e:
            logger.debug(f"SSD detection failed: {e}")
    
    # Dry-run mode
    if dry_run:
        logger.info("Dry-run mode: Simulating secure wipe without changes.")
        for path in resolved_paths:
            logger.info(f"Would securely wipe: {path}")
        logger.info("=== Secure Wipe Simulated (Dry-Run) ===")
        return
    
    # Confirmation prompt (unless no_confirm)
    if not no_confirm:
        logger.warning("This operation is IRREVERSIBLE and will securely delete the following paths:")
        for path in resolved_paths:
            logger.warning(f"  - {path}")
        print("Are you sure you want to proceed? This cannot be undone! (y/n): ", end='', file=sys.stderr)
        response = input().strip().lower()
        if not response.startswith('y'):
            logger.info("User aborted secure wipe.")
            return
    
    # Perform wipe
    wiped_files = 0
    wiped_dirs = 0
    for path in resolved_paths:
        if path.is_file():
            _wipe_file(path, method, passes, logger)
            wiped_files += 1
        elif path.is_dir():
            _wipe_dir(path, method, passes, logger)
            wiped_dirs += 1
        else:
            logger.warning(f"Skipping non-file/dir: {path}")
    
    logger.info(f"Secure wipe completed: {wiped_files} files and {wiped_dirs} directories wiped.")
    logger.info("=== Secure Wipe Completed ===")

def _get_patterns(method: str, passes: int, logger: logging.Logger) -> List[Tuple[any, bool]]:
    """
    Get the list of patterns for the method.
    Each tuple: (pattern: bytes or 'random', verify: bool)
    """
    if method == 'dod':
        return [
            (b'\x00', False),  # All zeros
            (b'\xFF', False),  # All ones
            ('random', True)   # Random + verify
        ]
    elif method == 'simple':
        return [('random', False)]
    elif method == 'gutmann':
        # Gutmann 35-pass method patterns
        return [
            ('random', False),
            ('random', False),
            ('random', False),
            ('random', False),
            (b'\x55', False),
            (b'\xAA', False),
            (b'\x92\x49\x24', False),
            (b'\x49\x24\x92', False),
            (b'\x24\x92\x49', False),
            (b'\x00', False),
            (b'\x11', False),
            (b'\x22', False),
            (b'\x33', False),
            (b'\x44', False),
            (b'\x55', False),
            (b'\x66', False),
            (b'\x77', False),
            (b'\x88', False),
            (b'\x99', False),
            (b'\xAA', False),
            (b'\xBB', False),
            (b'\xCC', False),
            (b'\xDD', False),
            (b'\xEE', False),
            (b'\xFF', False),
            (b'\x92\x49\x24', False),
            (b'\x49\x24\x92', False),
            (b'\x24\x92\x49', False),
            (b'\x6D\xB6\xDB', False),
            (b'\xB6\xDB\x6D', False),
            (b'\xDB\x6D\xB6', False),
            ('random', False),
            ('random', False),
            ('random', False),
            ('random', False),
        ]
    else:
        logger.warning(f"Unknown method '{method}'; falling back to {passes} random passes.")
        return [('random', False)] * passes

def _wipe_file(file_path: Path, method: str, passes: int, logger: logging.Logger) -> None:
    """Securely wipe a single file."""
    try:
        size = file_path.stat().st_size
        if size == 0:
            os.remove(file_path)
            logger.info(f"Removed empty file: {file_path}")
            return
        
        patterns = _get_patterns(method, passes, logger)
        
        with file_path.open('rb+') as f:
            for i, (pat, verify) in enumerate(patterns, 1):
                logger.debug(f"Pass {i}/{len(patterns)} for {file_path}")
                f.seek(0)
                remaining = size
                while remaining > 0:
                    chunk = min(remaining, CHUNK_SIZE)
                    if pat == 'random':
                        data = secrets.token_bytes(chunk)
                    else:
                        pat_len = len(pat)
                        full_chunks = chunk // pat_len
                        rem = chunk % pat_len
                        data = (pat * full_chunks) + pat[:rem]
                    
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                    
                    if verify:
                        f.seek(f.tell() - chunk)  # Seek back to start of chunk
                        read_data = f.read(chunk)
                        if read_data != data:
                            raise ValueError(f"Verification failed on pass {i} for {file_path}")
                        f.seek(f.tell())  # Seek forward to end of chunk
                    
                    remaining -= chunk
        
        # Truncate to 0, rename to random name, then remove
        with file_path.open('r+') as f:
            f.truncate(0)
        random_name = file_path.parent / (secrets.token_hex(8) + file_path.suffix)
        file_path.rename(random_name)
        os.remove(random_name)
        logger.info(f"Securely wiped file: {file_path}")
    except PermissionError:
        logger.error(f"Permission denied for {file_path}. Skipping (file may be in use).")
    except Exception as e:
        logger.error(f"Error wiping {file_path}: {str(e)}")

def _wipe_dir(dir_path: Path, method: str, passes: int, logger: logging.Logger) -> None:
    """Recursively wipe a directory."""
    for root, dirs, files in os.walk(dir_path, topdown=False):
        for file in files:
            file_p = Path(root) / file
            _wipe_file(file_p, method, passes, logger)
        for d in dirs:
            d_p = Path(root) / d
            try:
                os.rmdir(d_p)
                logger.debug(f"Removed empty dir: {d_p}")
            except OSError as e:
                logger.warning(f"Could not remove dir {d_p}: {str(e)}")
    try:
        os.rmdir(dir_path)
        logger.info(f"Removed dir: {dir_path}")
    except Exception as e:
        logger.error(f"Error removing dir {dir_path}: {str(e)}")