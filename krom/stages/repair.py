import logging
import os
import subprocess
import platform
import winreg  # For registry tweaks
from tqdm import tqdm  # For progress bars; already in dependencies
import time  # For duration timing

from krom.utils.backup import create_backup, restore_backup  # Updated to match backup.py
from krom.utils.system import is_admin  # Assume stubbed in utils/system.py

def run_subprocess_with_streaming(cmd, logger: logging.Logger, verbose: bool = False, desc: str = "Processing", input_data: str = None, timeout: int = 1800):
    """
    Helper to run a subprocess with live streaming of output and tqdm spinner for indefinite progress.
    Supports sending input via stdin (e.g., for prompts). Updates on each line; logs/info/warns based on verbosity.
    Adds timeout to prevent indefinite hangs.
    """
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE if input_data else None, text=True, bufsize=1)
    
    if input_data:
        process.stdin.write(input_data)
        process.stdin.close()
    
    if verbose:
        pbar = tqdm(desc=desc, total=None, dynamic_ncols=True, bar_format='{desc}: {elapsed} | {bar}')  # Spinner for unknown duration
    
    lines_processed = 0
    last_stdout_line = ""  # Track last non-empty stdout line
    for line in iter(process.stdout.readline, ''):
        stripped_line = line.strip()
        if stripped_line:  # Avoid empty lines
            if verbose:
                tqdm.write(stripped_line)  # Use tqdm.write to avoid bar disruption
                lines_processed += 1
            logger.info(stripped_line)
            last_stdout_line = stripped_line  # Update last
    
    # Stream stderr (for errors/warnings)
    for line in iter(process.stderr.readline, ''):
        stripped_line = line.strip()
        if stripped_line:
            if verbose:
                tqdm.write(stripped_line)
                lines_processed += 1
            logger.warning(stripped_line)  # Or error if critical
    
    process.stdout.close()
    process.stderr.close()
    
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.error(f"Command {' '.join(cmd)} timed out after {timeout}s; terminating.")
        process.terminate()
        if verbose:
            pbar.close()
        raise
    
    if verbose:
        pbar.close()
    
    return_code = process.returncode
    if return_code != 0:
        logger.warning(f"Command {' '.join(cmd)} returned non-zero exit status {return_code}. Check logs for details.")
    
    return return_code, last_stdout_line

def run_repair(args, config, logger: logging.Logger):
    """
    Repair stage: Fix system files, permissions, and network issues.
    Based on KromFeaturesOverview.md and KromCLIOverview.md.
    """
    if platform.system() != 'Windows':
        logger.warning("Repair stage is Windows-only; skipping.")
        return

    dry_run = args.dry_run
    verbose = getattr(args, 'verbose', config.get('verbose', False))  # Fallback to config
    offline = getattr(args, 'offline', False)  # Respect --offline
    interactive = getattr(args, 'interactive', False)  # For wizard prompts

    if not is_admin():
        logger.error("Repair stage requires admin privileges; skipping.")
        return

    logger.info("Starting Repair stage...")

    # Define steps for overall progress
    steps = [
        ("SFC /scannow", "SFC Repair"),
        ("DISM /RestoreHealth", "DISM Repair") if not offline else None,
        ("chkdsk", "CHKDSK Repair"),
        ("Network Fixes", "Network Repair"),
        ("Registry Tweaks", "Registry Repair")
    ]
    steps = [s for s in steps if s]  # Skip offline-skipped

    pbar = None
    if not dry_run and verbose:
        pbar = tqdm(total=len(steps), desc="Repair Progress", dynamic_ncols=True)

    needs_reboot = False  # Track if reboot is recommended

    for step_name, desc in steps:
        start_time = time.time()
        if pbar:
            pbar.set_description(f"Repair: {desc}")
        try:
            if step_name == "SFC /scannow":
                if dry_run:
                    logger.info("[Dry Run] Would run SFC /scannow to repair system files.")
                else:
                    cmd = ['sfc', '/scannow']
                    logger.info("Running SFC /scannow...")
                    _, _ = run_subprocess_with_streaming(cmd, logger, verbose=verbose, desc=desc)  # Ignore last_line

            elif step_name == "DISM /RestoreHealth":
                if dry_run:
                    logger.info("[Dry Run] Would run DISM /RestoreHealth.")
                else:
                    cmd = ['DISM', '/Online', '/Cleanup-Image', '/RestoreHealth']
                    logger.info("Running DISM /RestoreHealth...")
                    _, _ = run_subprocess_with_streaming(cmd, logger, verbose=verbose, desc=desc)

            elif step_name == "chkdsk":
                drives_to_check = getattr(args, 'drives_to_check', config.get('stages', {}).get('repair', {}).get('drives_to_check', ['C:']))  # CLI/config override
                for drive in drives_to_check:
                    if dry_run:
                        logger.info(f"[Dry Run] Would schedule chkdsk /f /r on {drive} for next boot.")
                    else:
                        cmd = ['chkdsk', drive, '/f', '/r']
                        logger.info(f"Running chkdsk /f /r on {drive}...")
                        return_code, last_stdout_line = run_subprocess_with_streaming(cmd, logger, verbose=verbose, desc=desc, input_data='Y\n')
                        logger.info(f"chkdsk completed or scheduled for {drive}.")
                        if 'Cannot lock current drive.' in last_stdout_line:
                            needs_reboot = True
                            logger.info(f"Drive {drive} locked; scheduled for next boot.")
                            if interactive:
                                reboot_confirm = input("Reboot now to run chkdsk? (y/n): ").strip().lower()
                                if reboot_confirm == 'y':
                                    subprocess.run(['shutdown', '/r', '/t', '0'], check=True)
                                else:
                                    logger.info(f"chkdsk scheduled for {drive} on next boot. Reboot manually to apply.")

            elif step_name == "Network Fixes":
                if dry_run:
                    logger.info("[Dry Run] Would reset network stack and flush DNS.")
                else:
                    network_cmds = [
                        (['netsh', 'int', 'ip', 'reset'], "TCP/IP stack reset."),
                        (['ipconfig', '/flushdns'], "DNS cache flushed."),
                        (['ipconfig', '/release'], "IP released."),
                        (['ipconfig', '/renew'], "IP renewed.")
                    ]
                    for cmd, success_msg in network_cmds:
                        logger.info(f"Running {' '.join(cmd)}...")
                        return_code, last_stdout_line = run_subprocess_with_streaming(cmd, logger, verbose=verbose, desc=desc)
                        logger.info(success_msg)
                        if 'Restart the computer' in last_stdout_line:
                            needs_reboot = True
                            logger.warning("*** REBOOT REQUIRED to apply network changes ***")

            elif step_name == "Registry Tweaks":
                reg_tweaks = getattr(args, 'reg_tweaks', config.get('stages', {}).get('repair', {}).get('reg_tweaks', [
                    (r'SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System', 'LocalAccountTokenFilterPolicy', 'DWORD', 1)  # Use raw string to handle backslashes literally
                ]))  # CLI/config override
                targets = [f"HKLM\\{key_path}" for key_path, _, _, _ in reg_tweaks]  # Backup targets
                original_paths = {target: target.replace('HKLM\\', '') for target in targets}  # For restore, but registry uses .reg import
                backup_path = create_backup('pre_repair_registry', config, logger, dry_run, targets=targets, original_paths=original_paths)
                for key_path, value_name, value_type, value_data in reg_tweaks:
                    # Normalize: Strip accidental r' or quotes
                    key_path = key_path.strip("r'\"")
                    if dry_run:
                        logger.info(f"[Dry Run] Would set registry: HKLM\\{key_path}\\{value_name} = {value_data}")
                    else:
                        try:
                            # Validate and normalize subkey
                            if not key_path.startswith('SOFTWARE\\'):  # Example validation; adjust as needed
                                raise ValueError(f"Invalid key_path: {key_path}")
                            subkey = key_path if not key_path.startswith('HKLM\\') else key_path[5:]
                            key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, subkey, 0, winreg.KEY_SET_VALUE)
                            if value_type == 'DWORD':
                                winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, value_data)
                            elif value_type == 'SZ':
                                winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, value_data)
                            # Add more types as needed
                            winreg.CloseKey(key)
                            logger.info(f"Applied registry tweak: HKLM\\{key_path}\\{value_name}")
                        except Exception as e:
                            logger.error(f"Failed to apply registry tweak HKLM\\{key_path}: {e}")
                            restore_backup('pre_repair_registry', config, logger, dry_run, backup_path=backup_path, original_paths=original_paths)  # Restore on error

            duration = time.time() - start_time
            logger.info(f"{desc}: {int(duration // 60):02d}:{int(duration % 60):02d} |")
            if pbar:
                pbar.update(1)
        except Exception as e:
            logger.error(f"Error in step '{step_name}': {e}")
            # Continue to next step; rollback only for registry

    if pbar:
        pbar.close()

    # Post-stage reboot prompt if needed and interactive
    if needs_reboot and interactive:
        reboot_confirm = input("Some changes (e.g., CHKDSK, network reset) require a reboot. Reboot now? (y/n): ").strip().lower()
        if reboot_confirm == 'y':
            subprocess.run(['shutdown', '/r', '/t', '0'], check=True)
        else:
            logger.warning("*** REBOOT RECOMMENDED to apply all changes ***")

    # Optional: Hook for enhancements like driver_audit if enabled
    if getattr(args, 'driver_audit', False) or config.get('enhancements', {}).get('driver_audit', {}).get('enabled', False):
        logger.info("Driver Audit enhancement enabled; running checks.")
        try:
            from krom.enhancements.driver_audit import run_driver_audit
            run_driver_audit(args, config, logger)
        except ImportError:
            logger.warning("driver_audit.py not implemented; skipping.")

    logger.info("Repair stage completed.")