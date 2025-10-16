import logging
import os
import subprocess
import platform
import psutil  # For disk and memory info

def run_optimize(args, config, logger: logging.Logger):
    """
    Optimize stage: Defrag drives (skip SSDs), reset pagefile, and trim resources.
    Based on KromFeaturesOverview.md and KromCLIOverview.md.
    """
    if platform.system() != 'Windows':
        logger.warning("Optimize stage is Windows-only; skipping.")
        return

    dry_run = args.dry_run

    logger.info("Starting Optimize stage...")

    # Step 1: Defrag drives (only for HDDs; skip SSDs)
    for partition in psutil.disk_partitions():
        drive = partition.device
        usage = psutil.disk_usage(drive)
        logger.info(f"Checking drive {drive} (Filesystem: {partition.fstype}, Total: {usage.total / (1024**3):.2f} GB)")

        # Detect if SSD (heuristic: check if rotational or use wmic)
        try:
            is_ssd = False
            cmd = ['wmic', 'diskdrive', 'get', 'MediaType', '/value']
            result = subprocess.run(cmd, capture_output=True, text=True)
            if 'SSD' in result.stdout.upper() or 'SOLID STATE' in result.stdout.upper():
                is_ssd = True
            if is_ssd:
                logger.info(f"Drive {drive} is SSD; running TRIM instead of defrag.")
                if dry_run:
                    logger.info(f"[Dry Run] Would run TRIM on {drive}")
                else:
                    try:
                        subprocess.run(['defrag', drive, '/L'], check=True)  # /L for TRIM on SSDs
                        logger.info(f"TRIM completed on {drive}")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"Failed to TRIM {drive}: {e}")
            else:
                logger.info(f"Drive {drive} is HDD; running defrag.")
                if dry_run:
                    logger.info(f"[Dry Run] Would defrag {drive}")
                else:
                    try:
                        subprocess.run(['defrag', drive, '/O'], check=True)  # /O for optimize (defrag or TRIM)
                        logger.info(f"Defrag completed on {drive}")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"Failed to defrag {drive}: {e}")
        except Exception as e:
            logger.error(f"Failed to check/detect drive type for {drive}: {e}")

    # Step 2: Reset pagefile (e.g., set to system-managed or custom size via config)
    pagefile_settings = config.get('pagefile', {'min': 1024, 'max': 4096})  # Example: MB; default to system-managed if not set
    if pagefile_settings:
        if dry_run:
            logger.info(f"[Dry Run] Would reset pagefile to min={pagefile_settings['min']}MB, max={pagefile_settings['max']}MB")
        else:
            try:
                # Use wmic to set pagefile (requires admin)
                subprocess.run(['wmic', 'computersystem', 'where', 'name="%computername%"', 'set', 'AutomaticManagedPagefile=False'], check=True)
                subprocess.run(['wmic', 'pagefileset', 'where', 'name="C:\\\\pagefile.sys"', 'set', f'InitialSize={pagefile_settings["min"]},MaximumSize={pagefile_settings["max"]}'], check=True)
                logger.info("Pagefile reset to custom sizes. Reboot may be required.")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to reset pagefile: {e}")
    else:
        if dry_run:
            logger.info("[Dry Run] Would set pagefile to system-managed.")
        else:
            try:
                subprocess.run(['wmic', 'computersystem', 'where', 'name="%computername%"', 'set', 'AutomaticManagedPagefile=True'], check=True)
                logger.info("Pagefile set to system-managed.")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to set system-managed pagefile: {e}")

    # Step 3: Trim resources (e.g., clear standby memory, optimize services; simple example)
    if dry_run:
        logger.info("[Dry Run] Would trim resources (e.g., clear standby memory).")
    else:
        try:
            # Example: Use PowerShell to flush DNS and clear some caches
            subprocess.run(['powershell', '-Command', 'ipconfig /flushdns'], check=True)
            logger.info("DNS cache flushed.")
            # Add more trims, e.g., service optimizations via sc config
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to trim resources: {e}")

    # Optional: Hook for enhancements like startup_manager if enabled
    if getattr(args, 'startup_manager', False):
        logger.info("Startup Manager enhancement enabled; running audit.")
        # Call from enhancements/startup_manager.py if implemented
        # e.g., from enhancements.startup_manager import run_startup_manager
        # run_startup_manager(args, config, logger)
        pass  # Placeholder; implement separately

    logger.info("Optimize stage completed.")