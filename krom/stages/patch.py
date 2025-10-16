import logging
import os
import subprocess
import platform
import requests  # For potential API checks if online

def run_patch(args, config, logger: logging.Logger, offline=False):
    """
    Patch stage: Update system and common apps (e.g., 7-Zip). Use offline patches if provided.
    Based on KromFeaturesOverview.md and KromCLIOverview.md.
    Avoid full Windows Update; focus on lightweight patching.
    """
    if platform.system() != 'Windows':
        logger.warning("Patch stage is Windows-only; skipping.")
        return

    dry_run = args.dry_run
    offline_patches_dir = getattr(args, 'offline_patches', config.get('offline_patches', None))

    logger.info("Starting Patch stage...")

    # Step 1: System patches (e.g., run DISM for component store repair/updates if offline files provided)
    if offline_patches_dir:
        if not os.path.isdir(offline_patches_dir):
            logger.error(f"Offline patches directory not found: {offline_patches_dir}. Skipping.")
        else:
            for patch_file in os.listdir(offline_patches_dir):
                if patch_file.endswith('.msu') or patch_file.endswith('.cab'):  # Common patch formats
                    full_path = os.path.join(offline_patches_dir, patch_file)
                    if dry_run:
                        logger.info(f"[Dry Run] Would apply offline patch: {full_path}")
                    else:
                        try:
                            # Use DISM for offline patching (assumes image is current system)
                            cmd = ['DISM', '/Online', '/Add-Package', f'/PackagePath:{full_path}']
                            subprocess.run(cmd, check=True)
                            logger.info(f"Applied offline patch: {patch_file}")
                        except subprocess.CalledProcessError as e:
                            logger.error(f"Failed to apply {patch_file}: {e}")
    else:
        logger.info("No offline patches provided; skipping system patching or using online check.")

    # Step 2: Update common apps (e.g., 7-Zip; check for updates via API or winget if installed)
    if not offline:
        common_apps = config.get('common_apps', ['7-Zip'])  # Expand via config
        for app in common_apps:
            if app == '7-Zip':
                # Example: Check latest version via API (GitHub releases for 7-Zip)
                api_url = 'https://api.github.com/repos/ip7z/7zip/releases/latest'  # Unofficial but common; adjust
                if dry_run:
                    logger.info(f"[Dry Run] Would check for {app} update via API.")
                else:
                    try:
                        response = requests.get(api_url)
                        response.raise_for_status()
                        latest_version = response.json()['tag_name']
                        # Compare with installed (e.g., via registry or command)
                        installed_version = 'unknown'  # Placeholder: Implement check e.g., via '7z --version'
                        logger.info(f"{app} latest version: {latest_version} (installed: {installed_version})")
                        # If update needed, download and install (but keep lightweight; log suggestion only)
                        logger.warning(f"If update available, manually install {app} from official site.")
                    except requests.RequestException as e:
                        logger.error(f"Failed to check {app} update: {e}")
    else:
        logger.info("Offline mode enabled; skipping online app update checks.")

    # Step 3: Optional Windows Update check (lightweight: just check for critical updates, don't auto-install)
    if config.get('check_windows_updates', False):
        if not offline:
            if dry_run:
                logger.info("[Dry Run] Would check for Windows updates.")
            else:
                try:
                    # Use PowerShell to list available updates (requires admin)
                    cmd = ['powershell', '-Command', 'Get-WUList -MicrosoftUpdate']
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    logger.info(f"Available updates: {result.stdout}")
                    logger.warning("Updates listed but not installed automatically. Review and apply manually.")
                except Exception as e:
                    logger.error(f"Failed to check Windows updates: {e}")
        else:
            logger.info("Offline mode enabled; skipping Windows Update check.")

    logger.info("Patch stage completed.")