import logging
import os
import subprocess
import platform
import shutil  # For potential file removal
import re  # For parsing PS output
import psutil  # For process killing (existing dep)

from krom.utils.backup import create_backup  # For path backups
from krom.utils.system import is_admin  # For admin check

def parse_ps_output(output: str) -> list:
    """
    Simple parser for PowerShell task output: Extracts task names matching EvilAI patterns (e.g., GUIDs, Node.js args).
    Returns list of suspicious task names.
    """
    suspicious_tasks = []
    lines = output.splitlines()
    current_task = None
    in_task = False
    for line in lines:
        if line.startswith('=== '):
            current_task = line[4:-4].strip()  # Extract task name
            in_task = True
        elif in_task and line.startswith('State: '):
            state = line[7:].strip()
            if state == 'Ready':  # Only flag active ones
                # Check for EvilAI patterns: GUID-like names or Node.js in args
                if re.match(r'^(HealthCheck|sys_component_health)\{[A-F0-9-]+\}', current_task) or 'node.exe' in output:
                    suspicious_tasks.append(current_task)
            in_task = False
    return suspicious_tasks

def run_disinfect(args, config, logger: logging.Logger):
    """
    Disinfect stage: Scan and remove malware/adware using open-source tools or heuristics.
    Based on KromFeaturesOverview.md and KromCLIOverview.md.
    Now includes EvilAI-specific heuristic cleanup for Node.js droppers.
    """
    if platform.system() != 'Windows':
        logger.warning("Disinfect stage is Windows-only; skipping.")
        return

    dry_run = args.dry_run
    no_backup = args.no_backup
    offline = getattr(args, 'offline', False)
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

    # Step 4: EvilAI Heuristic Cleanup (NEW: Targeted for Node.js droppers; runs if enabled in config)
    evilai_config = config.get('stages', {}).get('disinfect', {}).get('heuristic_cleanups', [{}])[0].get('evilai', {})
    if evilai_config.get('enabled', False):
        logger.info("Running EvilAI heuristic cleanup...")
        if not is_admin():
            logger.warning("EvilAI cleanup requires admin privileges; skipping.")
            return

        # 4a: Detect suspicious tasks via PS query
        ps_query = '''
        Get-ScheduledTask | Where-Object {$_.Actions.Execute -like "*cmd*"} | ForEach-Object { 
            Write-Output "=== $($_.TaskName) ==="; 
            $_.Actions | ForEach-Object { Write-Output "Execute: $($_.Execute)"; Write-Output "Arguments: $($_.Arguments)" }; 
            Write-Output "State: $($_.State)"; Write-Output "" 
        }
        '''
        suspicious_tasks = []
        try:
            result = subprocess.run(['powershell', '-Command', ps_query], capture_output=True, text=True, check=True)
            suspicious_tasks = parse_ps_output(result.stdout)
            logger.info(f"Detected {len(suspicious_tasks)} suspicious tasks.")
        except subprocess.CalledProcessError as e:
            logger.error(f"PowerShell task query failed: {e}")
        except Exception as e:
            logger.error(f"Task detection failed: {e}")

        # 4b: Disable tasks
        for task in suspicious_tasks:
            if dry_run:
                logger.info(f"[Dry Run] Would disable task: {task}")
            else:
                try:
                    disable_cmd = ['powershell', '-Command', f'Disable-ScheduledTask -TaskName "{task}"']
                    subprocess.run(disable_cmd, check=True)
                    logger.info(f"Disabled suspicious task: {task}")
                except subprocess.CalledProcessError as e:
                    logger.warning(f"Failed to disable {task}: {e}")

        # 4c: Backup & Purge payload paths
        purge_paths = evilai_config.get('payload_paths', [])
        expanded_paths = [os.path.expandvars(p) for p in purge_paths]
        if not no_backup and expanded_paths:
            backup_targets = expanded_paths  # Backup dirs/files before purge
            backup_path = create_backup('disinfect_evilai', config, logger, dry_run, targets=backup_targets)
            if not backup_path:
                logger.warning("Backup failed; proceeding with caution.")

        for path in expanded_paths:
            if dry_run:
                logger.info(f"[Dry Run] Would purge EvilAI payload: {path}")
            else:
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                        logger.info(f"Purged EvilAI folder: {path}")
                    elif os.path.isfile(path) or os.path.islink(path):
                        os.remove(path)
                        logger.info(f"Purged EvilAI file: {path}")
                except Exception as e:
                    logger.warning(f"Failed to purge {path}: {e}")

        # 4d: Kill suspicious processes (e.g., node.exe tied to payloads)
        kill_processes = evilai_config.get('kill_processes', ['node.exe'])
        for proc in psutil.process_iter(['name', 'exe']):
            try:
                if proc.info['name'] in kill_processes and proc.info['exe']:
                    # Check if path matches suspicious patterns (basic string match)
                    if any(susp in proc.info['exe'] for susp in expanded_paths):
                        if dry_run:
                            logger.info(f"[Dry Run] Would kill suspicious {proc.info['name']} (PID: {proc.pid})")
                        else:
                            proc.kill()
                            logger.info(f"Killed suspicious {proc.info['name']} (PID: {proc.pid})")
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception) as e:
                logger.debug(f"Skipped process {proc.pid}: {e}")

        logger.info("EvilAI heuristic cleanup complete. Recommend changing sensitive passwords from a clean device.")

    logger.info("Disinfect stage completed.")