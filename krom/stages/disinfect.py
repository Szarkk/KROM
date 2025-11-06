import logging
import os
import subprocess
import platform
import shutil  # For potential file removal
import re  # For parsing PS output
import psutil  # For process killing (existing dep)
import hashlib  # For SHA256 hashing in heuristic fallback
from tqdm import tqdm  # For progress bars (existing dep)
import shlex  # For secure command splitting
try:
    import requests  # For optional tool downloads (add to requirements.txt if using; guarded by offline)
except ImportError:
    requests = None
    logging.warning("requests not installed; downloads disabled.")

try:
    import yara  # For heuristic patterns (add yara-python to requirements.txt)
except ImportError:
    yara = None
    logging.warning("yara-python not installed; heuristics limited to regex/hash.")

from krom.utils.backup import create_backup  # For path backups
from krom.utils.system import is_admin  # For admin check

def parse_ps_output(output: str) -> list:
    """
    JSON parser for PowerShell task output: Extracts task names matching EvilAI patterns (e.g., GUIDs, Node.js args).
    Returns list of suspicious task names.
    Handles single object or list from ConvertTo-Json.
    """
    suspicious_tasks = []
    try:
        # Note: PS might return a single object or a list
        tasks = json.loads(output)
        if not isinstance(tasks, list):
            tasks = [tasks]
            
        for task in tasks:
            if task.get('State') != 'Ready':
                continue

            task_name = task.get('TaskName', '')
            task_content = task_name.lower()
            
            # Build content string from all actions
            if 'Actions' in task:
                for action in task['Actions']:
                    task_content += f" {action.get('Execute', '')} {action.get('Arguments', '')}".lower()

            # Reliable regex logic
            if re.match(r'^(healthcheck|sys_component_health)\{[a-f0-9-]+\}', task_name) or 'node.exe' in task_content:
                suspicious_tasks.append(task_name)
                
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse PowerShell JSON output: {e}")
    
    return suspicious_tasks

def install_av_tool(tool: dict, config: dict, logger: logging.Logger, dry_run: bool = False, offline: bool = False) -> str:
    """
    Install AV tool if not detected; returns install path or None.
    Supports bundled fallback in temp_dir for partial offline.
    """
    detect_cmd = tool.get('detect_cmd', '')
    if detect_cmd and not dry_run:
        try:
            detect_parts = shlex.split(detect_cmd)
            result = subprocess.run(detect_parts, shell=False, capture_output=True, text=True, check=False)
            if 'installed' in result.stdout.lower() or result.returncode == 0:
                logger.info(f"{tool['name']} already installed.")
                return tool.get('install_path', f"C:\\{tool['name']}")
        except Exception as e:
            logger.debug(f"Detect failed for {tool['name']}: {e}")

    if offline:
        # Fallback: Check for bundled in temp_dir
        temp_dir = config.get('paths', {}).get('temp_dir', './temp')
        bundled_exe = os.path.join(temp_dir, f"{tool['name']}_setup.exe")
        if os.path.exists(bundled_exe):
            logger.info(f"Using bundled {tool['name']} installer.")
        else:
            logger.warning(f"Offline mode: Skipping {tool['name']} install (no bundle).")
            return None

    if dry_run:
        logger.info(f"[Dry Run] Would install {tool['name']} from {tool['download_url']}")
        return tool.get('install_path')

    if not requests and offline:
        logger.error("requests unavailable and offline; cannot install.")
        return None

    try:
        # Download if not offline/bundled
        if not offline:
            download_url = tool['download_url']
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            temp_dir = config.get('paths', {}).get('temp_dir', './temp')
            os.makedirs(temp_dir, exist_ok=True)
            temp_exe = os.path.join(temp_dir, f"{tool['name']}_setup.exe")
            with open(temp_exe, 'wb') as f:
                shutil.copyfileobj(response.raw, f)
            logger.info(f"Downloaded {tool['name']} to {temp_exe}")
            installer_path = temp_exe
        else:
            installer_path = bundled_exe

        # Install via cmd as list (shlex for args)
        install_cmd_str = tool.get('install_cmd', '')
        install_cmd_parts = shlex.split(install_cmd_str) if install_cmd_str else []
        full_install = [installer_path] + install_cmd_parts
        result = subprocess.run(full_install, shell=False, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error(f"{tool['name']} install failed: {result.stderr}")
            return None
        if not offline:
            os.remove(temp_exe)  # Cleanup
        logger.info(f"{tool['name']} installed successfully.")
        return tool.get('install_path', f"C:\\{tool['name']}")
    except Exception as e:
        logger.error(f"Failed to install {tool['name']}: {e}")
        return None

def update_av_tool(tool: dict, logger: logging.Logger, dry_run: bool = False, offline: bool = False) -> bool:
    """
    Update tool signatures if supported.
    """
    update_cmd_list = tool.get('update_cmd_list', [])
    if not update_cmd_list:
        logger.info(f"{tool['name']} has no update command; skipping.")
        return True

    if offline:
        logger.warning(f"Offline: Skipping {tool['name']} update.")
        return True

    if dry_run:
        logger.info(f"[Dry Run] Would update {tool['name']}")
        return True

    try:
        result = subprocess.run(update_cmd_list, shell=False, capture_output=True, text=True, check=False)
        logger.info(f"{tool['name']} update: {result.stdout}")
        logger.debug(f"{tool['name']} update stderr: {result.stderr}")
        return result.returncode == 0
    except Exception as e:
        logger.warning(f"{tool['name']} update failed: {e}")
        return False

def enable_realtime_protection(tool: dict, logger: logging.Logger, dry_run: bool = False) -> bool:
    """
    Enable real-time protection for 'protector' tools (e.g., Malwarebytes service start).
    Idempotent: Skips if already running.
    """
    realtime_cmd_list = tool.get('realtime_enable_cmd_list', [])
    if not realtime_cmd_list:
        logger.info(f"{tool['name']} has no realtime enable command; skipping.")
        return True

    if dry_run:
        logger.info(f"[Dry Run] Would enable real-time protection for {tool['name']}")
        return True

    try:
        # Assume cmd is for service start; query first for idempotency
        # Extract service name heuristically (e.g., from cmd like "sc start MBAMService")
        service_name = realtime_cmd_list[-1] if realtime_cmd_list[0:2] == ['sc', 'start'] else 'MBAMService'
        query_cmd = ['sc', 'query', service_name]
        result = subprocess.run(query_cmd, shell=False, capture_output=True, text=True, check=False)
        logger.debug(f"Service query for {service_name}: {result.stdout}")
        if 'RUNNING' in result.stdout.upper():
            logger.info(f"{tool['name']} real-time protection already active.")
            return True

        # Enable
        result = subprocess.run(realtime_cmd_list, shell=False, capture_output=True, text=True, check=False)
        logger.info(f"{tool['name']} real-time protection enabled temporarily: {result.stdout}")
        return result.returncode == 0
    except Exception as e:
        logger.warning(f"Failed to enable {tool['name']} real-time: {e}")
        return False

def run_av_scan(tool: dict, scan_paths: list, logger: logging.Logger, dry_run: bool = False, offline: bool = False, non_interactive: bool = False) -> bool:
    """
    Run scan for a single tool: CLI if possible.
    Skips for protectors.
    """
    tool_type = tool.get('type', 'scanner')
    if tool_type == 'protector':
        logger.info(f"{tool['name']} is a protector; realtime enable handled separately.")
        return True

    tool_name = tool['name']
    scan_cmd_list = tool.get('scan_cmd_list')
    if scan_cmd_list is None:
        logger.warning(f"{tool_name} has no scan command; skipping.")
        return True

    logger.info(f"Running headless scan with {tool_name}...")
    for path in scan_paths:
        if dry_run:
            logger.info(f"[Dry Run] Would scan {path} with {tool_name}")
        else:
            try:
                # Just replace the token in the list, Python handles the spaces
                full_cmd = [arg.replace('%SCAN_PATH%', path) for arg in scan_cmd_list]
                
                # shell=False is still critical
                result = subprocess.run(full_cmd, shell=False, capture_output=True, text=True, check=False)
                logger.info(f"{tool_name} scan on {path}: {result.stdout}")
                logger.debug(f"{tool_name} scan stderr: {result.stderr}")
                if result.returncode != 0:
                    logger.warning(f"{tool_name} scan warning: {result.returncode}")
            except Exception as e:
                logger.error(f"{tool_name} scan on {path} failed: {e}")
    return True

def heuristic_scan(paths: list, rules_path: str, logger: logging.Logger, dry_run: bool = False, known_bad_hashes: list = None) -> list:
    """
    YARA-based heuristic scan; falls back to regex/hash if YARA unavailable.
    Returns list of (path, matches) tuples.
    """
    threats = []
    if known_bad_hashes is None:
        known_bad_hashes = []

    # YARA primary (if available)
    if yara and os.path.exists(rules_path):
        try:
            rules = yara.compile(rules_path)
            for path in tqdm(paths, desc="YARA Heuristic Scan"):
                if os.path.isfile(path):
                    matches = rules.match(path)
                    if matches:
                        threats.append((path, matches))
                        if not dry_run:
                            logger.warning(f"YARA threat detected: {path} (rules: {matches})")
                        else:
                            logger.info(f"[Dry Run] YARA hit on {path}: {matches}")
        except Exception as e:
            logger.error(f"YARA scan failed: {e}")

    # Fallback: SHA256 hash check for known bad hashes (chunked for large files)
    if known_bad_hashes:
        for path in tqdm(paths, desc="Fallback Heuristic Scan"):
            if os.path.isfile(path):
                try:
                    hasher = hashlib.sha256()
                    with open(path, 'rb') as f:
                        while chunk := f.read(65536):  # Chunked read for memory efficiency
                            hasher.update(chunk)
                    file_hash = hasher.hexdigest()
                    if file_hash in known_bad_hashes:
                        threats.append((path, ["Known bad hash match"]))
                        if not dry_run:
                            logger.warning(f"Known bad hash detected: {path} ({file_hash})")
                        else:
                            logger.info(f"[Dry Run] Known bad hash hit on {path}: {file_hash}")
                except Exception as e:
                    logger.debug(f"Hash calc failed on {path}: {e}")

    return threats

def run_disinfect(args, config, logger: logging.Logger):
    """
    Disinfect stage: Scan and remove malware/adware using open-source tools or heuristics.
    Based on KromFeaturesOverview.md and KromCLIOverview.md.
    Supports general AV tools + optional EvilAI-specific cleanup.
    """
    if platform.system() != 'Windows':
        logger.warning("Disinfect stage is Windows-only; skipping.")
        return

    if not is_admin():
        logger.warning("Disinfect stage requires admin privileges; skipping to avoid failures.")
        return

    dry_run = args.dry_run
    no_backup = args.no_backup
    offline = getattr(args, 'offline', False)
    scan_tool = getattr(args, 'scan_tool', None)  # Limit to specific tool if flagged
    keep_av = getattr(args, 'keep_av', False)  # NEW: Override to retain tools post-stage
    # Assume interactive unless standalone/scheduled
    interactive = not getattr(args, 'standalone', False)

    logger.info("Starting Disinfect stage...")

    # Step 1: Prepare scan paths (e.g., system dirs; customizable via config)
    disinfect_config = config.get('stages', {}).get('disinfect', {})
    scan_paths = disinfect_config.get('scan_paths', [os.path.expandvars('%SystemRoot%'), os.path.expandvars('%TEMP%'), os.path.expanduser('~')])
    logger.info(f"Scanning paths: {', '.join(scan_paths)}")

    # Step 2: Pre-AV backup for tool paths (safety)
    if not no_backup and not dry_run:
        av_paths = [tool.get('install_path', f"C:\\{tool['name']}") for tool in disinfect_config.get('av_tools', []) if tool.get('install_path')]
        expanded_av_paths = [os.path.expandvars(p) for p in av_paths if p]
        if expanded_av_paths:
            backup_path = create_backup('disinfect_av', config, logger, dry_run, targets=expanded_av_paths)
            if backup_path:
                logger.info(f"Pre-AV backups created: {backup_path}")

    # Step 3: Run multi-tool AV scans (Loop over av_tools; install/update/scan or enable per-tool)
    av_tools = disinfect_config.get('av_tools', [])
    if scan_tool:  # CLI override: Limit to specified tool
        av_tools = [t for t in av_tools if t['name'].lower() == scan_tool.lower()]
        logger.info(f"Limited to tool: {scan_tool}")
    if not av_tools:
        logger.warning("No AV tools configured; skipping scans.")
    else:
        for tool in av_tools:
            tool_name = tool['name']
            logger.info(f"Processing {tool_name}...")

            # Install if needed
            install_path = install_av_tool(tool, config, logger, dry_run, offline)
            if not install_path:
                logger.warning(f"Skipping {tool_name} (install failed).")
                continue

            # Update signatures
            if not update_av_tool(tool, logger, dry_run, offline):
                logger.warning(f"{tool_name} update skipped; proceeding.")

            tool_type = tool.get('type', 'scanner')
            if tool_type == 'protector' and not keep_av:
                logger.warning(f"{tool_name} protector mode skipped (temp tool; use --keep-av to retain).")
            elif tool_type == 'protector' and keep_av:
                # Enable real-time if retaining
                if enable_realtime_protection(tool, logger, dry_run):
                    logger.info(f"{tool_name} real-time protection activated (retained via --keep-av).")
                else:
                    logger.warning(f"Failed to activate {tool_name} protection.")
            else:
                # Run scan for scanners
                non_interactive = not interactive
                success = run_av_scan(tool, scan_paths, logger, dry_run, offline, non_interactive)
                if not success:
                    logger.warning(f"{tool_name} scan failed; continuing.")

            # Always uninstall unless --keep-av
            should_uninstall = tool.get('uninstall_cmd') and not keep_av
            if tool.get('keep_installed') and keep_av:
                should_uninstall = False  # Config + flag both want to keep
            if should_uninstall:
                if dry_run:
                    logger.info(f"[Dry Run] Would uninstall {tool_name}")
                else:
                    try:
                        uninstall_cmd_parts = shlex.split(tool['uninstall_cmd'])
                        subprocess.run(uninstall_cmd_parts, shell=False, check=False)
                        logger.info(f"Uninstalled {tool_name} (temp tool).")
                    except Exception as e:
                        logger.warning(f"Uninstall {tool_name} failed: {e}")
            elif keep_av:
                logger.info(f"Retained {tool_name} post-scan (--keep-av).")

    # Step 4: Heuristic scan (YARA + fallback; post-AV)
    rules_path = disinfect_config.get('rules_path', './data/pup_rules.yar')
    known_bad_hashes = disinfect_config.get('known_bad_hashes', [])  # List of hex hashes
    threats = heuristic_scan(scan_paths, rules_path, logger, dry_run, known_bad_hashes)
    logger.info(f"Heuristic scan found {len(threats)} threats.")

    # Optional: Quarantine/Remove threats (config-driven)
    quarantine_dir = disinfect_config.get('quarantine_dir', './quarantine')
    if threats and not dry_run:
        os.makedirs(quarantine_dir, exist_ok=True)
        for path, matches in threats:
            try:
                quarantine_path = os.path.join(quarantine_dir, os.path.basename(path))
                shutil.move(path, quarantine_path)
                logger.info(f"Quarantined threat: {path} -> {quarantine_path} (matches: {matches})")
            except Exception as e:
                logger.error(f"Failed to quarantine {path}: {e}")

    # Step 5: Optional EvilAI Heuristic Cleanup (config-driven; runs post-heuristics)
    evilai_config = disinfect_config.get('evilai', {})
    if evilai_config.get('enabled', False):
        logger.info("Running EvilAI heuristic cleanup...")

        # 5a: Backup purge paths first
        purge_paths = evilai_config.get('payload_paths', [])
        expanded_paths = [os.path.expandvars(p) for p in purge_paths]
        if not no_backup and expanded_paths:
            backup_targets = expanded_paths  # Backup dirs/files before purge
            backup_path = create_backup('disinfect_evilai', config, logger, dry_run, targets=backup_targets)
            if not backup_path:
                logger.warning("Backup failed; proceeding with caution.")

        # 5b: Detect suspicious tasks via PS query (with -ErrorAction SilentlyContinue)
        ps_query = '''
        Get-ScheduledTask -ErrorAction SilentlyContinue | 
            Where-Object {$_.Actions.Execute -like "*cmd*"} | 
            Select-Object TaskName, @{N="Actions";E={$_.Actions}}, State | 
            ConvertTo-Json
        '''
        suspicious_tasks = []
        try:
            if dry_run:
                logger.info("[Dry Run] Would query tasks.")
            else:
                result = subprocess.run(['powershell', '-Command', ps_query], capture_output=True, text=True, check=False)
                logger.debug(f"PS query stderr: {result.stderr}")
                suspicious_tasks = parse_ps_output(result.stdout)
                logger.info(f"Detected {len(suspicious_tasks)} suspicious tasks.")
        except Exception as e:
            logger.error(f"Task detection failed: {e}")

        # 5c: Disable tasks
        for task in tqdm(suspicious_tasks, desc="Disabling Tasks") if logger.level == logging.DEBUG else suspicious_tasks:
            if dry_run:
                logger.info(f"[Dry Run] Would disable task: {task}")
            else:
                try:
                    disable_cmd = ['powershell', '-Command', f'Disable-ScheduledTask -TaskName "{task}"']
                    subprocess.run(disable_cmd, shell=False, check=False)
                    logger.info(f"Disabled suspicious task: {task}")
                except subprocess.CalledProcessError as e:
                    logger.warning(f"Failed to disable {task}: {e}")

        # 5d: Purge payload paths
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

        # 5e: Kill suspicious processes (e.g., node.exe tied to payloads)
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