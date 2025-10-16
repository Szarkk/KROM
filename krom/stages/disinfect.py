import logging
import os
import subprocess
import platform
import shutil  # For potential file removal

def run_disinfect(args, config, logger: logging.Logger):
    """
    Disinfect stage: Scan and remove malware/adware using open-source tools or heuristics.
    Based on KromFeaturesOverview.md and KromCLIOverview.md.
    """
    if platform.system() != 'Windows':
        logger.warning("Disinfect stage is Windows-only; skipping.")
        return

    dry_run = args.dry_run
    scan_tool = getattr(args, 'scan_tool', config.get('scan_tool', 'clamav'))  # Default to clamav; customizable

    logger.info("Starting Disinfect stage...")

    # Step 1: Prepare scan paths (e.g., system dirs; customizable via config)
    scan_paths = config.get('scan_paths', [os.path.expandvars('%SystemRoot%'), os.path.expandvars('%TEMP%'), os.path.expanduser('~')])
    logger.info(f"Scanning paths: {', '.join(scan_paths)}")

    # Step 2: Run malware scan based on tool
    if scan_tool.lower() == 'clamav':
        # Assume ClamAV is installed (e.g., via chocolatey or manual); use clamscan.exe
        clamscan_path = shutil.which('clamscan')  # Find in PATH
        if not clamscan_path:
            logger.error("ClamAV not found in PATH. Install ClamAV or use another tool. Skipping scan.")
            return

        for path in scan_paths:
            if dry_run:
                logger.info(f"[Dry Run] Would scan path with ClamAV: {path}")
            else:
                try:
                    # Run clamscan with remove option (-r for recursive, --remove for auto-remove)
                    cmd = [clamscan_path, '-r', '--remove=yes', '--no-summary', path]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    logger.info(f"ClamAV scan on {path}: {result.stdout}")
                    if result.returncode != 0:
                        logger.warning(f"ClamAV returned non-zero code: {result.returncode}. Check logs.")
                except Exception as e:
                    logger.error(f"Failed to run ClamAV on {path}: {e}")
    else:
        logger.warning(f"Unsupported scan tool: {scan_tool}. Falling back to basic heuristic scan.")

    # Step 3: Simple heuristic scan for known bad files (as fallback or addition)
    known_bad_files = config.get('known_bad_files', ['example_virus.exe', 'malware.dll'])  # Load from config
    for path in scan_paths:
        for root, _, files in os.walk(path):
            for file in files:
                if file in known_bad_files:
                    full_path = os.path.join(root, file)
                    if dry_run:
                        logger.info(f"[Dry Run] Would remove known bad file: {full_path}")
                    else:
                        try:
                            os.remove(full_path)
                            logger.info(f"Removed known bad file: {full_path}")
                        except Exception as e:
                            logger.error(f"Failed to remove {full_path}: {e}")

    logger.info("Disinfect stage completed.")