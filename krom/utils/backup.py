import logging
import os
import shutil
import subprocess
import time  # For retries
from datetime import datetime

# Simple in-memory tracker for backups (stage_name -> (backup_path, original_path)); for persistence, could write to a file
BACKUP_TRACKER = {}

def _manual_copytree(src, dst, logger, ignore_errors=False, max_retries=3):
    """Manual copytree to handle ignore_errors by skipping problematic files with retries."""
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        for d in dirs:
            os.makedirs(os.path.join(dst, os.path.relpath(os.path.join(root, d), src)), exist_ok=True)
        for f in files:
            src_file = os.path.join(root, f)
            dst_file = os.path.join(dst, os.path.relpath(src_file, src))
            retries = max_retries
            while retries > 0:
                try:
                    shutil.copy2(src_file, dst_file)
                    break
                except Exception as e:
                    if ignore_errors and ('WinError 32' in str(e) or 'Errno 13' in str(e)):  # Locked/permission
                        logger.warning(f"Skipped locked/permission file during backup (no closure attempted): {src_file} ({e})")
                        break
                    elif ignore_errors:
                        logger.warning(f"Skipped file during backup: {src_file} ({e})")
                        break
                    else:
                        logger.warning(f"Backup file issue: {src_file} ({e}). Retrying...")
                        time.sleep(1)
                        retries -= 1
            if retries == 0:
                logger.error(f"Failed to copy {src_file} after {max_retries} retries; skipping.")

def create_registry_backup(backup_path: str, logger: logging.Logger, dry_run: bool = False) -> bool:
    if dry_run:
        logger.info(f"[Dry Run] Would export registry to {backup_path}")
        return True
    try:
        subprocess.run(['reg', 'export', 'HKLM', backup_path, '/y'], check=True)
        logger.info(f"Registry backed up to {backup_path}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to backup registry: {e}")
        return False

def create_file_backup(src_path: str, dest_path: str, logger: logging.Logger, dry_run: bool = False, max_retries: int = 3, ignore_errors: bool = False) -> bool:
    if dry_run:
        logger.info(f"[Dry Run] Would backup {src_path} to {dest_path}")
        return True
    try:
        if not os.path.exists(src_path):
            raise FileNotFoundError(f"Source path not found: {src_path}")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        _manual_copytree(src_path, dest_path, logger, ignore_errors=ignore_errors, max_retries=max_retries)
        logger.info(f"Backed up {src_path} to {dest_path} (partial if skips occurred)")
        return True
    except FileNotFoundError as e:
        logger.error(f"Backup failed due to missing source: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to backup {src_path}: {e}")
        return False

def restore_registry_backup(backup_path: str, logger: logging.Logger, dry_run: bool = False) -> bool:
    if dry_run:
        logger.info(f"[Dry Run] Would import registry from {backup_path}")
        return True
    try:
        subprocess.run(['reg', 'import', backup_path], check=True)
        logger.info(f"Registry restored from {backup_path}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to restore registry: {e}")
        return False

def restore_file_backup(backup_path: str, original_path: str, logger: logging.Logger, dry_run: bool = False) -> bool:
    if dry_run:
        logger.info(f"[Dry Run] Would restore {backup_path} to {original_path}")
        return True
    try:
        shutil.copytree(backup_path, original_path, dirs_exist_ok=True)
        logger.info(f"Restored {backup_path} to {original_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to restore {original_path}: {e}")
        return False

def create_backup(stage_name: str, config: dict, logger: logging.Logger, dry_run: bool = False, targets: list = None, original_paths: dict = None) -> str:
    """
    Generalized backup creation: Delegates to registry/file based on target type.
    Returns base_backup_path if successful. Supports multiple targets.
    """
    if targets is None:
        targets = []
    if original_paths is None:
        original_paths = {}
    backup_dir = config.get('paths', {}).get('backups', './backups')
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_backup_path = os.path.join(backup_dir, f"{stage_name}_backup_{timestamp}")

    # Expand targets to resolve env vars and user ~
    expanded_targets = [os.path.expandvars(os.path.expanduser(t)) for t in targets]
    if logger.level == logging.DEBUG:  # Verbose check
        logger.debug(f"Expanded backup targets: {expanded_targets}")

    backup_paths = []
    success_count = 0
    ignore_errors = config.get('stages', {}).get(stage_name, {}).get('backup_ignore_errors', True)  # Default True for skips
    for idx, target in enumerate(expanded_targets):
        orig_target = targets[idx]  # Keep original for original_paths if needed
        if target.startswith('HK'):  # Registry target
            backup_path = f"{base_backup_path}_{target.replace('HKLM\\', '').replace('\\', '_')}.reg"  # Unique per target
            if create_registry_backup(backup_path, logger, dry_run):
                backup_paths.append(backup_path)
                success_count += 1
        else:  # File/dir
            backup_path = f"{base_backup_path}_{os.path.basename(target)}"
            if create_file_backup(target, backup_path, logger, dry_run, ignore_errors=ignore_errors):
                backup_paths.append(backup_path)
                success_count += 1
    
    # Track for restore: Store list of paths and originals (update originals with expanded if exists)
    for k in list(original_paths.keys()):
        original_paths[k] = os.path.expandvars(os.path.expanduser(original_paths[k]))
    BACKUP_TRACKER[stage_name] = (backup_paths, original_paths)

    # Return path only if at least one succeeded
    return base_backup_path if success_count > 0 else None

def restore_backup(stage_name: str, config: dict, logger: logging.Logger, dry_run: bool = False, backup_path: str = None, original_paths: dict = None) -> bool:
    """
    Restore from backup: Looks up from tracker or provided path, delegates to specific restore.
    Handles multiple backups if tracked.
    """
    if backup_path is None:
        tracked = BACKUP_TRACKER.get(stage_name)
        if tracked is None:
            logger.warning(f"No backup found for {stage_name}. Skipping restore.")
            return False
        backup_paths, tracked_originals = tracked
        if original_paths is None:
            original_paths = tracked_originals
    else:
        backup_paths = [backup_path]

    success = True
    for bp in backup_paths:
        if bp.endswith('.reg'):
            if not restore_registry_backup(bp, logger, dry_run):
                success = False
        else:
            # For file: Use original_path from dict (keyed by target or bp)
            orig = original_paths.get(bp, None)
            if orig is None:
                logger.warning(f"No original_path for {bp}; skipping file restore.")
                success = False
                continue
            if not restore_file_backup(bp, orig, logger, dry_run):
                success = False
    return success