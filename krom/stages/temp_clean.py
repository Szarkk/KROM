import logging
import os
import shutil
import subprocess
import platform
import time  # For retry sleep (fallback only)
import psutil  # For finding locking processes (interactive only)
from tqdm import tqdm  # For progress bars (fallback only)
from pathlib import Path  # For path handling
import fnmatch  # For robust pattern matching (fallback only)
from krom.utils.backup import create_backup, restore_backup  # For backups and restore
from krom.utils.system import is_admin, run_as_admin  # For admin checks
from krom.enhancements.browser_cleanup import run_browser_cleanup  # Enhancement hook

def run_temp_clean(args, config, logger: logging.Logger):
    """
    Temp Clean stage: Wipe temp files, browser caches, event logs, and update caches.
    Based on KromFeaturesOverview.md and KromCLIOverview.md.
    Supports CLI overrides like --temp-dirs, --skip-patterns (add to main.py argparse).
    """
    if platform.system() != 'Windows':
        logger.warning("Temp Clean stage is Windows-only; skipping.")
        return

    # Check admin privileges
    if not is_admin():
        logger.warning("Temp Clean requires admin privileges for full access (e.g., event logs).")
        # Enhanced relaunch: Pass stage callback (stub; implement in system.py for full relaunch with args)
        def stage_callback():
            run_temp_clean(args, config, logger)
        run_as_admin(logger, stage_callback)  # Attempt relaunch if not dry-run

    dry_run = args.dry_run
    verbose = getattr(args, 'verbose', config.get('verbose', False))
    interactive = getattr(args, 'interactive', False)
    no_backup = getattr(args, 'no_backup', config.get('no_backup', False))
    offline = getattr(args, 'offline', False)  # For any network-guarded ops

    # Config alignment: Pull from stages.temp_clean
    tc_config = config.get('stages', {}).get('temp_clean', {})
    use_native = tc_config.get('use_native_commands', True)  # Default to fast native mode
    temp_dirs_raw = getattr(args, 'temp_dirs', []) or tc_config.get('temp_dirs', [
        '%TEMP%',
        '%SystemRoot%\\Temp',
        '~\\AppData\\Local\\Temp'
    ])
    # Expand paths universally and remove duplicates
    temp_dirs = list(set([os.path.expandvars(os.path.expanduser(d)) for d in temp_dirs_raw]))
    if verbose:
        logger.debug(f"Expanded and unique temp_dirs: {temp_dirs}")

    # Support CLI --skip-patterns (add to main.py: parser.add_argument('--skip-patterns', nargs='+'))
    skip_patterns = getattr(args, 'skip_patterns', []) or tc_config.get('skip_patterns', ['*.lock', 'pdf24*', '.ses'])
    event_logs = tc_config.get('event_logs', ['Application', 'Security', 'System'])
    update_cache_dirs_raw = tc_config.get('update_cache_dirs', ['%SystemRoot%\\SoftwareDistribution\\Download'])
    # Expand paths universally and remove duplicates
    update_cache_dirs = list(set([os.path.expandvars(os.path.expanduser(d)) for d in update_cache_dirs_raw]))
    if verbose:
        logger.debug(f"Expanded and unique update_cache_dirs: {update_cache_dirs}")

    max_retries = tc_config.get('max_retries', 3)  # Fallback only
    backup_required = tc_config.get('backup_required', False)  # Halt if backups fail?
    force_delete_locked = tc_config.get('force_delete_locked', False)  # Fallback only

    logger.info("Starting Temp Clean stage...")

    backup_path = None
    original_paths = {}  # For restore
    error_occurred = False  # Flag for conditional restore
    try:
        # Backup integration: Create backups for temp dirs, update caches (event logs not backed up as they're logs)
        if not no_backup:
            targets = temp_dirs + update_cache_dirs
            # Match backup naming: {basename: full_path}
            original_paths = {os.path.basename(t): t for t in targets if Path(t).exists()}
            if verbose:
                logger.debug(f"Backup targets: {targets}")
            backup_path = create_backup('temp_clean', config, logger, dry_run=dry_run, targets=targets, original_paths=original_paths)
            if not backup_path and not dry_run:
                logger.warning("Backup failed (likely due to locked files); proceeding with caution.")
                if interactive and backup_required:
                    continue_prompt = input("Backups failed—continue anyway? (y/n): ").strip().lower()
                    if continue_prompt != 'y':
                        logger.error("Aborting Temp Clean due to backup failure.")
                        return
        else:
            logger.warning("Backups skipped due to --no-backup.")

        # Step 1: Wipe temp files in specified directories
        deleted_mb = 0  # Track space freed (rough)
        skipped_locked = []  # For summary (native mode logs via output)
        for dir_path in temp_dirs:
            if not Path(dir_path).exists():
                logger.warning(f"Temp directory not found: {dir_path}. Skipping.")
                continue

            logger.info(f"Cleaning temp directory: {dir_path}")

            # UPDATED: Pre-clean size and count for metrics (dir-specific via rglob for accuracy)
            if dry_run:
                pre_size_mb = 0
                pre_file_count = 0
            else:
                try:
                    all_items = list(Path(dir_path).rglob('*'))
                    pre_file_count = len([f for f in all_items if f.is_file()])
                    pre_size_mb = sum(f.stat().st_size for f in all_items if f.is_file()) / (1024 * 1024)
                except Exception as size_e:
                    logger.warning(f"Could not calculate pre-size/count for {dir_path}: {size_e}")
                    pre_size_mb = 0
                    pre_file_count = 0
            if verbose:
                logger.debug(f"Pre-clean: {pre_file_count} files, {pre_size_mb:.1f} MB")

            if use_native:
                # FAST NATIVE MODE: Bulk delete via cmd (Tron-like: del files, then rd dirs)
                if dry_run:
                    logger.info(f"[Dry Run] Would run native bulk clean on: {dir_path}")
                    if verbose:
                        logger.debug(f"[Dry Run] Commands: del /f /s /q \"{dir_path}\\*\" 2>nul && for /r \"{dir_path}\" %i in (*) do @if exist \"%i\\\" rd /s /q \"%i\" 2>nul")
                else:
                    cmd1 = ['cmd', '/c', f'del /f /s /q /a "{dir_path}\\*" 2>nul']  # UPDATED: /a for attributes (hidden/system files)
                    cmd2 = ['cmd', '/c', f'for /r "{dir_path}" %i in (*) do @if exist "%i\\" rd /s /q "%i" 2>nul']  # UPDATED: Full recurse on root, check if dir before rd
                    try:
                        result1 = subprocess.run(cmd1, capture_output=True, text=True, check=False)
                        if result1.returncode != 0:
                            logger.warning(f"Native del returned non-zero ({result1.returncode}): {result1.stderr.strip() or 'No stderr (likely locks/empty)'}")
                        else:
                            if verbose and result1.stderr:
                                logger.debug(f"Native del output: {result1.stderr.strip()}")

                        result2 = subprocess.run(cmd2, capture_output=True, text=True, check=False)
                        if result2.returncode != 0:
                            logger.warning(f"Native rd returned non-zero ({result2.returncode}): {result2.stderr.strip() or 'No stderr (likely locks)'}")
                            skipped_locked.append(dir_path)  # Track if rd fails
                        else:
                            if verbose and result2.stderr:
                                logger.debug(f"Native rd output: {result2.stderr.strip()}")

                        logger.info(f"Native bulk clean completed for: {dir_path}")
                    except Exception as cmd_e:
                        logger.error(f"Native clean failed for {dir_path}: {cmd_e}")
                        skipped_locked.append(dir_path)  # Track for summary
                        error_occurred = True  # Only true exceptions trigger restore

                # UPDATED: Post-clean size and count for metrics (dir-specific via rglob)
                if dry_run:
                    post_size_mb = pre_size_mb
                    post_file_count = pre_file_count
                else:
                    try:
                        all_items = list(Path(dir_path).rglob('*'))
                        post_file_count = len([f for f in all_items if f.is_file()])
                        post_size_mb = sum(f.stat().st_size for f in all_items if f.is_file()) / (1024 * 1024)
                    except Exception as size_e:
                        logger.warning(f"Could not calculate post-size/count for {dir_path}: {size_e}")
                        post_size_mb = pre_size_mb
                        post_file_count = pre_file_count
                freed_mb = pre_size_mb - post_size_mb
                deleted_mb += freed_mb
                if verbose:
                    logger.debug(f"Post-clean: {post_file_count} files left, freed {freed_mb:.1f} MB ({pre_file_count - post_file_count} files)")
                # NEW: Diag if 0 freed on non-empty
                if freed_mb <= 0 and pre_size_mb > 0:
                    logger.warning(f"No space freed in {dir_path} (pre: {pre_size_mb:.1f} MB)—likely locks; run Prep stage or Safe Mode for better results.")
            else:
                # FALLBACK: Original walk logic (for custom skips, etc.)
                deleted_count = 0
                skipped_by_pattern = []  # Full paths
                skipped_locked_fallback = []  # Full paths (separate for fallback)
                for root, dirs, files in tqdm(os.walk(dir_path, topdown=False), desc=f"Scanning {dir_path}", disable=not verbose):
                    # Delete files first
                    for file in files:
                        full_path = os.path.join(root, file)
                        if any(fnmatch.fnmatch(file, pattern) for pattern in skip_patterns):
                            if verbose:
                                logger.debug(f"Skipped (matches pattern): {full_path}")
                            skipped_by_pattern.append(full_path)
                            continue
                        
                        if dry_run:
                            if verbose:
                                logger.debug(f"[Dry Run] Would delete file: {full_path}")
                            deleted_count += 1
                            continue

                        retries = max_retries
                        while retries > 0:
                            try:
                                if force_delete_locked:
                                    # Windows-friendly lock break: Rename trick
                                    tmp_path = full_path + '.kromtmp'
                                    os.rename(full_path, tmp_path)
                                    os.remove(tmp_path)
                                else:
                                    os.remove(full_path)
                                if verbose:
                                    logger.debug(f"Deleted file: {full_path}")
                                deleted_count += 1
                                break
                            except OSError as e:
                                if e.winerror in (5, 32) or e.errno in (13, 16):  # Access denied/locked
                                    logger.debug(f"File locked: {full_path} ({e}). Retrying...")
                                    time.sleep(1)
                                    retries -= 1
                                else:
                                    logger.error(f"Failed to delete {full_path}: {e}")
                                    break
                            except Exception as e:
                                logger.error(f"Unexpected error deleting {full_path}: {e}")
                                break
                        
                        if retries == 0:
                            logger.info(f"Failed to delete locked file after retries: {full_path}")
                            skipped_locked_fallback.append(full_path)
                            # Integrate helpers: Find and offer to kill processes
                            locking_procs = find_locking_processes(full_path)
                            if interactive and locking_procs:
                                safe_procs = [p for p in locking_procs if is_safe_to_kill(p)]
                                if safe_procs:
                                    for proc in safe_procs:
                                        confirm = input(f"Kill process locking {os.path.basename(full_path)}? ({proc.name()} PID {proc.pid}) (y/n): ").strip().lower()
                                        if confirm == 'y':
                                            try:
                                                proc.kill()
                                                logger.info(f"Killed {proc.name()} (PID: {proc.pid})")
                                            except Exception as kill_e:
                                                logger.error(f"Failed to kill {proc.name()}: {kill_e}")

                    # Delete directories (bottom-up, only if empty)
                    for d in dirs[:]:  # Copy to avoid modification during iteration
                        full_dir = os.path.join(root, d)
                        if dry_run:
                            if verbose:
                                logger.debug(f"[Dry Run] Would delete directory: {full_dir}")
                            deleted_count += 1
                            continue

                        retries = max_retries
                        while retries > 0:
                            try:
                                if force_delete_locked:
                                    # Fallback to rmtree for stubborn dirs
                                    shutil.rmtree(full_dir, ignore_errors=False)
                                else:
                                    os.rmdir(full_dir)  # Fails if not empty
                                if verbose:
                                    logger.debug(f"Deleted directory: {full_dir}")
                                deleted_count += 1
                                break
                            except OSError as e:
                                if e.winerror in (5, 32) or e.errno in (13, 16):  # Locked/not empty/access denied
                                    logger.debug(f"Directory locked/not empty: {full_dir} ({e}). Retrying...")
                                    time.sleep(1)
                                    retries -= 1
                                else:
                                    logger.error(f"Failed to delete {full_dir}: {e}")
                                    break
                            except Exception as e:
                                logger.error(f"Unexpected error deleting {full_dir}: {e}")
                                break
                        
                        if retries == 0:
                            logger.info(f"Failed to delete locked directory after retries: {full_dir}")
                            skipped_locked_fallback.append(full_dir)
                            # Integrate helpers
                            locking_procs = find_locking_processes(full_dir)
                            if interactive and locking_procs:
                                safe_procs = [p for p in locking_procs if is_safe_to_kill(p)]
                                if safe_procs:
                                    for proc in safe_procs:
                                        confirm = input(f"Kill process locking {os.path.basename(full_dir)}? ({proc.name()} PID {proc.pid}) (y/n): ").strip().lower()
                                        if confirm == 'y':
                                            try:
                                                proc.kill()
                                                logger.info(f"Killed {proc.name()} (PID: {proc.pid})")
                                            except Exception as kill_e:
                                                logger.error(f"Failed to kill {proc.name()}: {kill_e}")
                deleted_mb += deleted_count * 0.001  # Rough estimate; improve if fallback used
                # Fallback summary additions (if used)
                skipped_locked += skipped_locked_fallback  # Merge to main list

        # UPDATED: Summary (adapted for native: Focus on MB freed, skipped dirs; add remnant count)
        remnant_count = 0
        if verbose:
            for dir_path in temp_dirs:
                try:
                    # UPDATED: Depth=1 recurse for better remnant estimate (quick)
                    for root, dirs, files in os.walk(dir_path, topdown=True):
                        remnant_count += len(files) + len(dirs)
                        if root != dir_path:  # Limit to one level deep
                            break
                except OSError:
                    pass  # Dir gone or inaccessible
            logger.debug(f"Post-clean remnants: ~{remnant_count} items (depth 1) across dirs")
        # UPDATED: Flag skipped if remnants high
        if remnant_count > 5:
            if 'high_remnants' not in skipped_locked:
                skipped_locked.append('high_remnants')
        logger.info(f"Temp clean summary: Freed ~{deleted_mb:.1f} MB, skipped {len(skipped_locked)} locked dirs (remnants: ~{remnant_count}).")
        if verbose and skipped_locked:
            logger.debug(f"Skipped locked: {', '.join(skipped_locked)}")

        # Optional interactive for many skips (native mode: Scan post-clean for remnants)
        if interactive and len(skipped_locked) > 0:
            confirm = input(f"Locked remnants found ({len(skipped_locked)})—try killing related processes? (y/n): ").strip().lower()
            if confirm == 'y':
                for path in skipped_locked[:3]:  # Limit
                    if path == 'high_remnants':
                        logger.info("High remnants detected—manual check recommended.")
                        continue
                    locking_procs = find_locking_processes(path)
                    safe_procs = [p for p in locking_procs if is_safe_to_kill(p)]
                    if safe_procs:
                        for proc in safe_procs:
                            sub_confirm = input(f"Kill {proc.name()} (PID {proc.pid}) for {os.path.basename(path)}? (y/n): ").strip().lower()
                            if sub_confirm == 'y':
                                try:
                                    proc.kill()
                                    logger.info(f"Killed {proc.name()} (PID: {proc.pid})")
                                except Exception as kill_e:
                                    logger.error(f"Failed to kill {proc.name()}: {kill_e}")

        # Step 2: Clear event logs (using wevtutil) - Unchanged
        for log in event_logs:
            if dry_run:
                logger.info(f"[Dry Run] Would clear event log: {log}")
            else:
                try:
                    subprocess.run(['wevtutil', 'cl', log], check=True)
                    logger.info(f"Cleared event log: {log}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to clear {log}: {e}")

        # Step 3: Clear update caches - Unchanged, but add native if desired
        for dir_path in update_cache_dirs:
            if Path(dir_path).exists():
                if dry_run:
                    logger.info(f"[Dry Run] Would clear update cache: {dir_path}")
                else:
                    try:
                        shutil.rmtree(dir_path, ignore_errors=True)
                        os.makedirs(dir_path)  # Recreate empty dir
                        logger.info(f"Cleared update cache: {dir_path}")
                    except Exception as e:
                        logger.error(f"Failed to clear {dir_path}: {e}")

        # Enhancement: Browser cleanup if enabled - Unchanged
        if not offline and getattr(args, 'browser_cleanup', tc_config.get('browser_cleanup', {}).get('enabled', False)):
            browsers = getattr(args, 'browsers', tc_config.get('browser_cleanup', {}).get('browsers', ['chrome', 'firefox', 'edge']))
            logger.info(f"Browser Cleanup enhancement enabled for: {', '.join(browsers)}")
            run_browser_cleanup(args, config, logger, browsers=browsers)  # Explicitly pass browsers

    except Exception as stage_e:
        logger.error(f"Unexpected error in Temp Clean: {stage_e}")
        error_occurred = True
        raise
    finally:
        # Restore only on error (not always)
        if backup_path and not dry_run and error_occurred:
            logger.info("Restoring from backup due to error.")
            restore_backup('temp_clean', config, logger, dry_run=dry_run, backup_path=backup_path, original_paths=original_paths)

    logger.info("Temp Clean stage completed.")

def find_locking_processes(file_path):
    """Find processes locking a file using psutil."""
    locking_procs = []
    try:
        for proc in psutil.process_iter(['open_files']):
            try:
                for f in proc.open_files():
                    if os.path.normcase(f.path) == os.path.normcase(file_path):
                        locking_procs.append(proc)
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except KeyboardInterrupt:
        raise  # Propagate to outer handler
    return locking_procs

def is_safe_to_kill(proc):
    """Basic check if process is safe to kill (e.g., not system-critical like winlogon.exe)."""
    critical_processes = ['winlogon.exe', 'csrss.exe', 'smss.exe', 'lsass.exe', 'services.exe', 'system']  # Expand as needed
    return proc.name().lower() not in critical_processes