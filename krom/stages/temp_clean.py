import logging
import os
import shutil
import subprocess
import platform
import time  # For retry sleep (aggressive only)
import psutil  # For finding locking processes (interactive only)
import sys  # For stderr in tqdm
from tqdm import tqdm  # For progress bars (aggressive fallback only)
from pathlib import Path  # For path handling
import fnmatch  # For robust pattern matching (fallback only)
from krom.utils.backup import create_backup, restore_backup  # For backups and restore
from krom.utils.system import is_admin, run_as_admin  # For admin checks
from krom.stages.prep import run_prep  # Optional: Import for auto-hook
from krom.enhancements.browser_cleanup import run_browser_cleanup  # Enhancement hook


def _get_dir_stats(dir_path: str, logger: logging.Logger, verbose: bool = False) -> tuple[int, float]:
    """
    Get file count and total size (MB) for a directory.
    """
    file_count = 0
    total_size_mb = 0.0
    if not Path(dir_path).exists():
        return 0, 0.0
    try:
        for root, _, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    stat = os.stat(file_path)
                    file_count += 1
                    total_size_mb += stat.st_size / (1024 * 1024)  # MB
                except (OSError, PermissionError):
                    if verbose:
                        logger.debug(f"Skipped stat for {file_path} (access denied)")
                    pass
    except Exception as e:
        if verbose:
            logger.debug(f"Stats scan failed for {dir_path}: {e}")
    return file_count, total_size_mb


def _bulk_native_clean(dir_path: str, logger: logging.Logger, dry_run: bool = False, verbose: bool = False) -> bool:
    """
    Fast native bulk delete using cmd /c del /f /s /q.
    Returns True if successful (rc==0), False otherwise (fallback trigger).
    """
    if dry_run:
        logger.info(f"[Dry Run] Would bulk clean: {dir_path}")
        return True
    # Normalize path to fix double backslashes
    norm_path = os.path.normpath(dir_path.replace('\\\\', '\\'))
    cmd = ['cmd', '/c', 'del', '/f', '/s', '/q', f'"{norm_path}\\*.*"']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            logger.info(f"Native bulk clean completed for: {dir_path}")
            return True
        else:
            if verbose:
                logger.debug(f"Native del returned non-zero ({result.returncode}): {result.stderr or 'No stderr (likely locks/empty)'}")
            return False
    except Exception as e:
        logger.warning(f"Bulk clean failed for {dir_path}: {e}")
        return False


def _per_file_clean(dir_path: str, logger: logging.Logger, dry_run: bool = False, aggressive: bool = False,
                    max_retries: int = 3, skip_patterns: list = None, verbose: bool = False) -> tuple[int, int, list]:
    """
    Fallback per-file walk: Delete unlocked files, skip/log locks.
    If aggressive=True, retry on PermissionError. Returns (deleted_count, skipped_count, skipped_files_list).
    """
    if skip_patterns is None:
        skip_patterns = []
    deleted_count = 0
    skipped_count = 0
    skipped_files = []  # For batched logging
    if dry_run:
        logger.info(f"[Dry Run] Would per-file clean: {dir_path} (aggressive: {aggressive})")
        return 0, 0, []

    try:
        for root, _, files in tqdm(list(os.walk(dir_path)), desc="Per-file clean", disable=not (verbose and not dry_run), file=sys.stderr):
            for file in files:
                file_path = os.path.join(root, file)
                # Skip patterns
                if any(fnmatch.fnmatch(file, pat) for pat in skip_patterns):
                    skipped_count += 1
                    continue
                retries = max_retries if aggressive else 0
                while retries >= 0:
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                        break
                    except PermissionError as pe:
                        if retries > 0:
                            time.sleep(1)
                            retries -= 1
                        else:
                            skipped_count += 1
                            skipped_files.append(file_path)
                            break
                    except OSError as ose:
                        if ose.winerror == 32:  # Sharing violation (locked)
                            skipped_count += 1
                            skipped_files.append(file_path)
                            break
                        else:
                            raise
                    except Exception as e:
                        logger.warning(f"Unexpected error deleting {file_path}: {e}")
                        skipped_count += 1
                        break
        # Batch log skips
        if verbose and skipped_files:
            top_skips = skipped_files[:5]
            logger.debug(f"Skipped {skipped_count} locked files (e.g., top 5: {top_skips})")
    except Exception as e:
        logger.error(f"Per-file clean failed for {dir_path}: {e}")
    return deleted_count, skipped_count, skipped_files


def _clear_event_logs(event_logs: list, logger: logging.Logger, dry_run: bool = False) -> None:
    """Clear Windows event logs using wevtutil."""
    for log in event_logs:
        if dry_run:
            logger.info(f"[Dry Run] Would clear event log: {log}")
        else:
            try:
                subprocess.run(['wevtutil', 'cl', log], check=True, capture_output=True)
                logger.info(f"Cleared event log: {log}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to clear {log}: {e}")


def _clear_update_cache(update_cache_dirs: list, logger: logging.Logger, dry_run: bool = False,
                        offline: bool = False, verbose: bool = False) -> float:
    """Clear Windows Update cache: Stop service if running, delete, restart. Returns freed MB."""
    freed_mb = 0.0
    service_name = 'wuauserv'
    for dir_path in update_cache_dirs:
        pre_count, pre_size = _get_dir_stats(dir_path, logger, verbose)
        if dry_run:
            logger.info(f"[Dry Run] Would clear update cache: {dir_path} (pre: {pre_count} files, {pre_size:.1f} MB)")
            freed_mb += pre_size
            continue
        if offline:
            logger.info(f"Offline mode: Skipping service ops for {dir_path}")
            continue
        was_running = False
        try:
            # Query service status
            query_result = subprocess.run(['sc', 'query', service_name], capture_output=True, text=True, check=False)
            if 'RUNNING' in query_result.stdout:
                was_running = True
                subprocess.run(['net', 'stop', service_name], check=True, capture_output=True)
                logger.debug(f"Stopped {service_name}")
            # Delete
            shutil.rmtree(dir_path, ignore_errors=False)
            # Recreate
            os.makedirs(dir_path, exist_ok=True)
            # Restart if was running
            if was_running:
                subprocess.run(['net', 'start', service_name], check=True, capture_output=True)
                logger.debug(f"Restarted {service_name}")
            logger.info(f"Cleared update cache: {dir_path}")
            # Post stats
            _, post_size = _get_dir_stats(dir_path, logger, verbose)
            delta_mb = pre_size - post_size
            freed_mb += delta_mb
            if verbose:
                logger.debug(f"Update cache {os.path.basename(dir_path)}: Pre {pre_count} files/{pre_size:.1f} MB → Post {post_size:.1f} MB (freed {delta_mb:.1f} MB)")
        except subprocess.CalledProcessError as e:
            logger.error(f"Service op failed for {dir_path}: {e}")
            # Fallback: Direct clean without service
            try:
                shutil.rmtree(dir_path, ignore_errors=True)
                os.makedirs(dir_path, exist_ok=True)
                logger.warning(f"Fallback direct clean for {dir_path}")
                _, post_size = _get_dir_stats(dir_path, logger, verbose)
                freed_mb += pre_size - post_size
            except Exception as fb_e:
                logger.error(f"Fallback failed for {dir_path}: {fb_e}")
        except Exception as e:
            logger.error(f"Failed to clear {dir_path}: {e}")
    return freed_mb


def _suggest_reboot(skipped_count: int, freed_mb: float, pre_total_mb: float, logger: logging.Logger,
                    interactive: bool = False, verbose: bool = False) -> None:
    """Suggest reboot if high skips/low free (locks likely)."""
    if skipped_count > 0:  # Always suggest if any skips and interactive
        ratio = freed_mb / pre_total_mb if pre_total_mb > 0 else 0
        msg = f"Locks respected (apps open?)—skipped {skipped_count} files, freed {ratio:.1%} ({freed_mb:.1f} MB of {pre_total_mb:.1f} MB). Close VS Code/Wondershare or reboot for deeper clean."
        if verbose:
            logger.warning(msg)
        if interactive:
            confirm = input(msg + " Reboot now? (y/n): ").strip().lower()
            if confirm == 'y':
                logger.info("Reboot suggested—run 'shutdown /r /t 0' manually.")
            else:
                logger.info("Tip: Use --safe-mode in Prep next.")


def find_locking_processes(file_path: str, logger: logging.Logger) -> list:
    """Find processes locking a specific file using psutil (for interactive)."""
    locking_procs = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'open_files']):
            try:
                for f in proc.open_files() or []:
                    if os.path.normcase(f.path) == os.path.normcase(file_path):
                        locking_procs.append(proc)
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        if logger.level <= logging.DEBUG:
            logger.debug(f"Lock scan failed for {file_path}: {e}")
    return locking_procs


def is_safe_to_kill(proc, logger: logging.Logger) -> bool:
    """Check if process is safe to kill (not critical)."""
    critical = {'winlogon.exe', 'csrss.exe', 'smss.exe', 'lsass.exe', 'services.exe', 'system idle process'}
    name_lower = proc.name().lower()
    safe = name_lower not in critical
    if not safe and logger.level <= logging.WARNING:
        logger.warning(f"Unsafe to kill critical process: {name_lower}")
    return safe


def run_temp_clean(args, config, logger: logging.Logger):
    """
    Temp Clean stage: Wipe temp files, browser caches, event logs, and update caches.
    Based on KromFeaturesOverview.md and KromCLIOverview.md.
    Supports CLI overrides like --temp_dirs, --skip_patterns (add to main.py argparse).
    """
    if platform.system() != 'Windows':
        logger.warning("Temp Clean stage is Windows-only; skipping.")
        return

    # Admin check and relaunch stub
    if not is_admin():
        logger.warning("Temp Clean requires admin for full access (e.g., %WINDIR%/Temp). Running partial.")

    dry_run = args.dry_run
    verbose = getattr(args, 'verbose', config.get('verbose', False))
    interactive = getattr(args, 'interactive', False)
    no_backup = getattr(args, 'no_backup', config.get('no_backup', False))
    offline = getattr(args, 'offline', False)

    # Config
    tc_config = config.get('stages', {}).get('temp_clean', {})
    use_native = tc_config.get('use_native_commands', True)
    temp_dirs_raw = getattr(args, 'temp_dirs', []) or tc_config.get('temp_dirs', [
        '%TEMP%', '%SystemRoot%\\Temp', '~\\AppData\\Local\\Temp'
    ])
    temp_dirs = list(set(os.path.normpath(os.path.expandvars(os.path.expanduser(d)).replace('\\\\', '\\')) for d in temp_dirs_raw))
    if verbose:
        logger.debug(f"Expanded and unique temp_dirs: {temp_dirs}")

    skip_patterns = getattr(args, 'skip_patterns', []) or tc_config.get('skip_patterns', ['*.lock', 'pdf24*', '.ses'])
    event_logs = tc_config.get('event_logs', ['Application', 'Security', 'System'])
    update_cache_dirs_raw = tc_config.get('update_cache_dirs', ['%SystemRoot%\\SoftwareDistribution\\Download'])
    update_cache_dirs = list(set(os.path.normpath(os.path.expandvars(os.path.expanduser(d)).replace('\\\\', '\\')) for d in update_cache_dirs_raw))
    if verbose:
        logger.debug(f"Expanded and unique update_cache_dirs: {update_cache_dirs}")

    aggressive = tc_config.get('aggressive_locks', False)
    max_retries = tc_config.get('max_retries', 3)
    backup_required = tc_config.get('backup_required', False)

    logger.info("Starting Temp Clean stage...")

    backup_path = None
    original_paths = {}
    error_occurred = False
    try:
        # Backups
        if not no_backup:
            targets = [t for t in temp_dirs + update_cache_dirs if Path(t).exists()]
            original_paths = {os.path.basename(t): t for t in targets}
            if verbose:
                logger.debug(f"Backup targets: {targets}")
            backup_path = create_backup('temp_clean', config, logger, dry_run=dry_run,
                                        targets=targets, original_paths=original_paths)
            if not backup_path and not dry_run:
                logger.warning("Backup partial/failed; proceeding.")
                if interactive and backup_required:
                    if input("Backups incomplete—continue? (y/n): ").strip().lower() != 'y':
                        return

        # Optional Prep hook for locks
        total_pre_files = sum(_get_dir_stats(d, logger, verbose)[0] for d in temp_dirs)
        if interactive and total_pre_files > 100:
            if input(f"Many files ({total_pre_files})—call Prep to clear locks? (y/n): ").strip().lower() == 'y':
                run_prep(args, config, logger)

        # Step 1: Temp dirs clean
        deleted_mb_total = 0.0
        skipped_locked = []
        pre_total_mb = sum(_get_dir_stats(d, logger, verbose)[1] for d in temp_dirs)
        remnant_count = 0
        remnant_breakdown = {}

        for dir_path in temp_dirs:
            if not Path(dir_path).exists():
                continue
            pre_count, pre_size = _get_dir_stats(dir_path, logger, verbose)
            if verbose:
                logger.debug(f"Pre-clean {os.path.basename(dir_path)}: {pre_count} files, {pre_size:.1f} MB")

            success = False
            if use_native:
                success = _bulk_native_clean(dir_path, logger, dry_run, verbose)
            if not success:
                del_count, skip_count, skipped_files = _per_file_clean(dir_path, logger, dry_run, aggressive,
                                                        max_retries, skip_patterns, verbose)
                if verbose:
                    logger.debug(f"Fallback {os.path.basename(dir_path)}: Deleted {del_count}, skipped {skip_count}")
                if skip_count > 0:
                    skipped_locked.append(os.path.basename(dir_path))
                if not aggressive and skip_count > pre_count * 0.5:
                    skipped_locked.append('high_locks')

            # Post stats
            post_count, post_size = _get_dir_stats(dir_path, logger, verbose)
            delta_mb = pre_size - post_size
            deleted_mb_total += delta_mb
            if verbose:
                logger.debug(f"Post-clean {os.path.basename(dir_path)}: {post_count} files, {post_size:.1f} MB (freed {delta_mb:.1f} MB)")

            # Remnants (immediate children only)
            dir_remnant = 0
            try:
                for root, dirs, files in os.walk(dir_path, topdown=True):
                    dir_remnant += len(files) + len(dirs)
                    if root != dir_path:
                        break
            except OSError:
                pass
            remnant_count += dir_remnant
            remnant_breakdown[os.path.basename(dir_path)] = dir_remnant

        if verbose:
            logger.debug(f"Post-clean remnants: ~{remnant_count} items (immediate children). Breakdown: {remnant_breakdown}")
        if remnant_count > 5:
            skipped_locked.append('high_remnants')
        logger.info(f"Temp clean summary: Freed ~{deleted_mb_total:.1f} MB from temps, skipped {len(skipped_locked)} dirs/issues (remnants: ~{remnant_count}).")
        if verbose and skipped_locked:
            logger.debug(f"Details: {', '.join(skipped_locked)}")

        _suggest_reboot(sum(len(Path(d).rglob('*')) for d in temp_dirs if skipped_locked), deleted_mb_total, pre_total_mb, logger, interactive, verbose)

        # Interactive proc kill if skips (aggressive only, safe procs)
        if interactive and aggressive and skipped_locked:
            for path_basename in skipped_locked[:3]:  # Limit
                if path_basename == 'high_remnants' or path_basename == 'high_locks':
                    continue
                dir_path = next((d for d in temp_dirs if os.path.basename(d) == path_basename), None)
                if dir_path:
                    # Sample a file for lock scan
                    sample_file = next((f for f in Path(dir_path).rglob('*') if f.is_file()), None)
                    if sample_file:
                        procs = find_locking_processes(str(sample_file), logger)
                        safe_procs = [p for p in procs if is_safe_to_kill(p, logger)]
                        for proc in safe_procs:
                            if input(f"Kill safe {proc.name()} (PID {proc.pid}) locking {path_basename}? (y/n): ").strip().lower() == 'y':
                                try:
                                    proc.kill()
                                    logger.info(f"Killed {proc.name()} (PID: {proc.pid})")
                                except Exception as e:
                                    logger.error(f"Kill failed: {e}")

        # Step 2: Event logs
        _clear_event_logs(event_logs, logger, dry_run)

        # Step 3: Update cache
        update_freed = _clear_update_cache(update_cache_dirs, logger, dry_run, offline, verbose)
        if verbose:
            logger.debug(f"Update cache freed: {update_freed:.1f} MB")

        # Enhancement: Browser cleanup
        bc_config = tc_config.get('browser_cleanup', {})
        if not offline and (getattr(args, 'browser_cleanup', False) or bc_config.get('enabled', False)):
            browsers = getattr(args, 'browsers', bc_config.get('browsers', ['chrome', 'firefox', 'edge']))
            logger.info(f"Running Browser Cleanup for: {', '.join(browsers)}")
            run_browser_cleanup(args, config, logger)  # Assumes it handles browsers internally

    except Exception as stage_e:
        logger.error(f"Unexpected error in Temp Clean: {stage_e}")
        error_occurred = True
        raise
    finally:
        if backup_path and not dry_run and error_occurred:
            logger.info("Restoring backups due to error.")
            restore_backup('temp_clean', config, logger, dry_run=False, backup_path=backup_path, original_paths=original_paths)

    total_freed = deleted_mb_total + update_freed
    logger.info(f"Temp Clean stage completed. Total freed: ~{total_freed:.1f} MB.")
    if total_freed < pre_total_mb * 0.8 and not is_admin():
        logger.warning("Low freed space—run as admin for full system Temp access.")