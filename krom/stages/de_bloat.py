import logging
import os
import subprocess
import platform
import json  # For potential list parsing if needed

def run_de_bloat(args, config, logger: logging.Logger):
    """
    De-Bloat stage: Remove pre-installed bloatware, unwanted apps, and disable telemetry/services.
    Based on KromFeaturesOverview.md and KromCLIOverview.md.
    """
    if platform.system() != 'Windows':
        logger.warning("De-Bloat stage is Windows-only; skipping.")
        return

    dry_run = args.dry_run
    bloat_list_file = args.bloat_list if hasattr(args, 'bloat_list') else config.get('bloat_list', None)

    logger.info("Starting De-Bloat stage...")

    # Step 1: Load bloatware list (default or custom)
    default_bloat_apps = [
        'Microsoft.BingWeather', 'Microsoft.GetHelp', 'Microsoft.Getstarted',
        'Microsoft.MicrosoftOfficeHub', 'Microsoft.MicrosoftSolitaireCollection',
        'Microsoft.People', 'Microsoft.SkypeApp', 'Microsoft.WindowsAlarms',
        'Microsoft.WindowsCamera', 'Microsoft.windowscommunicationsapps',
        'Microsoft.WindowsMaps', 'Microsoft.WindowsSoundRecorder', 'Microsoft.XboxApp',
        'Microsoft.YourPhone', 'Microsoft.ZuneMusic', 'Microsoft.ZuneVideo',
        'king.com.CandyCrushSaga'  # Example third-party
    ]  # Expand based on common lists; can load from YAML/JSON

    if bloat_list_file:
        try:
            with open(bloat_list_file, 'r') as f:
                custom_bloat = json.load(f) if bloat_list_file.endswith('.json') else f.read().splitlines()
            default_bloat_apps.extend(custom_bloat)
            logger.info(f"Loaded custom bloat list from {bloat_list_file}")
        except Exception as e:
            logger.error(f"Failed to load bloat list: {e}")
            logger.info("Falling back to default bloat list.")

    # Step 2: Remove apps (using PowerShell Get-AppxPackage/Remove-AppxPackage for UWP apps)
    for app in set(default_bloat_apps):  # Dedupe if custom overlaps
        if dry_run:
            logger.info(f"[Dry Run] Would remove app: {app}")
        else:
            try:
                # Check if installed
                check_cmd = ['powershell', '-Command', f'Get-AppxPackage -Name {app}']
                result = subprocess.run(check_cmd, capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    remove_cmd = ['powershell', '-Command', f'Get-AppxPackage -Name {app} | Remove-AppxPackage']
                    subprocess.run(remove_cmd, check=True)
                    logger.info(f"Removed bloatware app: {app}")
                else:
                    logger.debug(f"App {app} not found; skipping.")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to remove {app}: {e}")

    # Step 3: Disable unwanted services (e.g., telemetry-related)
    services_to_disable = ['DiagTrack', 'dmwappushservice']  # Connected User Experiences and Telemetry, WAP Push
    for service in services_to_disable:
        if dry_run:
            logger.info(f"[Dry Run] Would disable service: {service}")
        else:
            try:
                # Stop and disable
                subprocess.run(['sc', 'stop', service], check=False)  # check=False as may not be running
                subprocess.run(['sc', 'config', service, 'start=', 'disabled'], check=True)
                logger.info(f"Disabled service: {service}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to disable {service}: {e}")

    # Step 4: Disable telemetry via registry tweaks (use winreg for Python-native, but fallback to reg.exe)
    telemetry_reg_keys = [
        (r'HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection', 'AllowTelemetry', 'DWORD', 0),
        (r'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection', 'AllowTelemetry', 'DWORD', 0)
    ]
    import winreg  # Standard in Python on Windows
    for key_path, value_name, value_type, value_data in telemetry_reg_keys:
        if dry_run:
            logger.info(f"[Dry Run] Would set registry: {key_path}\\{value_name} = {value_data}")
        else:
            try:
                key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE)
                if value_type == 'DWORD':
                    winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, value_data)
                winreg.CloseKey(key)
                logger.info(f"Set registry to disable telemetry: {key_path}\\{value_name}")
            except Exception as e:
                logger.error(f"Failed to set registry {key_path}: {e}")

    logger.info("De-Bloat stage completed.")