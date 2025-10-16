import logging
import os
import subprocess
import psutil  # For process management
import platform
from krom.utils.backup import create_backup  # Use centralized backup utility

def run_prep(args, config, logger: logging.Logger):
    """
    Prep stage: Create backups, kill suspicious processes, and prepare for safe mode if needed.
    Based on KromFeaturesOverview.md and KromCLIOverview.md.
    Args:
        args: Parsed CLI arguments (Namespace from argparse)
        config: Configuration dict from default.yaml
        logger: Logging instance for console/file output
    """
    if platform.system() != 'Windows':
        logger.warning("Prep stage is Windows-only; skipping non-applicable parts.")
        return

    dry_run = args.dry_run
    no_backup = args.no_backup
    safe_mode = args.safe_mode
    interactive = getattr(args, 'interactive', False)  # For confirmations

    logger.info("Starting Prep stage...")

    # Step 1: Create backups (registry and key files)
    if not no_backup:
        # Use centralized backup utility from utils/backup.py
        backup_targets = ['HKLM', os.path.expanduser('~/Documents')]  # Registry and user docs
        original_paths = {os.path.join(config['paths']['backups'], 'documents_backup'): os.path.expanduser('~/Documents')}
        backup_path = create_backup(
            stage_name='prep',
            config=config,
            logger=logger,
            dry_run=dry_run,
            targets=backup_targets,
            original_paths=original_paths
        )
        if backup_path:
            logger.info(f"Backups created at {backup_path}")
        else:
            logger.error("Backup creation failed; proceeding with caution.")
    else:
        logger.warning("Backups skipped due to --no-backup flag.")

    # Step 2: Kill suspicious processes from config (with backward compat for string list)
    suspicious_processes = config.get('stages', {}).get('prep', {}).get('suspicious_processes', [])
    if not suspicious_processes:
        logger.warning("No suspicious processes defined in config; skipping process kill.")
    else:
        # Collect all processes with name and path
        procs = []
        for proc in psutil.process_iter(['name', 'exe']):
            try:
                proc_name = proc.info['name'].lower() if proc.info['name'] else ''
                proc_path = os.path.normcase(proc.info['exe']) if proc.info['exe'] else ''
                procs.append((proc_name, proc_path, proc.pid, proc))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass  # Skip inaccessible procs
        
        for susp in suspicious_processes:
            if isinstance(susp, str):  # Backward compat: Treat as name only, no path check, allow_multi=True
                name = susp.lower()
                legit_path = None
                allow_multi = True
            else:  # Dict: Use full options
                name = susp.get('name', '').lower()
                legit_path = os.path.normcase(os.path.expandvars(susp.get('legit_path', ''))) if susp.get('legit_path') else None
                allow_multi = susp.get('allow_multi', True)
            if not name:
                continue
            
            # Find matching procs
            matching_procs = [p for p in procs if p[0] == name or (susp.get('wildcard', False) and p[0].startswith(name[:-2] if name.endswith('.*') else name))]
            
            # Check multiples if not allowed
            if not allow_multi and len(matching_procs) > 1:
                logger.warning(f"Multiple instances of {name} found ({len(matching_procs)})—killing all but one.")
                for _, _, pid, proc in sorted(matching_procs, key=lambda x: x[2])[1:]:  # Keep lowest PID
                    if dry_run:
                        logger.info(f"[Dry Run] Would kill extra {name} (PID: {pid})")
                    else:
                        try:
                            proc.kill()
                            logger.info(f"Killed extra suspicious process: {name} (PID: {pid})")
                        except psutil.NoSuchProcess:
                            pass
                        except Exception as e:
                            logger.error(f"Failed to kill extra {name} (PID: {pid}): {e}")
            
            # Check path for each
            for proc_name, proc_path, pid, proc in matching_procs:
                if legit_path and legit_path not in proc_path:
                    if dry_run:
                        logger.info(f"[Dry Run] Would kill suspicious {proc_name} at invalid path {proc_path} (PID: {pid})")
                    else:
                        try:
                            proc.kill()
                            logger.info(f"Killed suspicious process {proc_name} at invalid path {proc_path} (PID: {pid})")
                        except psutil.NoSuchProcess:
                            pass
                        except Exception as e:
                            logger.error(f"Failed to kill {proc_name} at {proc_path} (PID: {pid}): {e}")
                elif not legit_path:  # No path check: Always kill if name matches
                    if dry_run:
                        logger.info(f"[Dry Run] Would kill {proc_name} (PID: {pid})")
                    else:
                        try:
                            proc.kill()
                            logger.info(f"Killed suspicious process: {proc_name} (PID: {pid})")
                        except psutil.NoSuchProcess:
                            pass
                        except Exception as e:
                            logger.error(f"Failed to kill {proc_name}: {e}")

    # Step 3: Prep for safe mode if enabled
    if safe_mode:
        if interactive:
            confirm = input("Prep for safe mode? This schedules safe boot on next reboot (y/n): ").strip().lower()
            if confirm != 'y':
                logger.info("Safe mode prep cancelled.")
                return
        if dry_run:
            logger.info("[Dry Run] Would prepare for safe mode reboot.")
        else:
            try:
                # Set safe boot with networking (requires admin)
                logger.warning("Scheduling safe mode—do not reboot yet. Run wrap_up or manual bcdedit to undo.")
                subprocess.run(['bcdedit', '/set', '{current}', 'safeboot', 'network'], check=True)
                logger.info("Safe mode prepared (networking enabled). Reboot required to enter. Undo with 'bcdedit /deletevalue {current} safeboot'.")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to set safe mode: {e}")
    else:
        logger.info("Safe mode prep skipped.")

    logger.info("Prep stage completed.")