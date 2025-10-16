import argparse
import logging
import os
import platform
import sys
from argparse import Namespace, ArgumentParser
from tqdm import tqdm  # For progress bar
import shutil  # For disk usage in storage calc
import psutil  # For partitions in storage calc
import inspect  # For function signature checks

# Import stages
from krom.stages.prep import run_prep
from krom.stages.temp_clean import run_temp_clean
from krom.stages.de_bloat import run_de_bloat
from krom.stages.disinfect import run_disinfect
from krom.stages.repair import run_repair
from krom.stages.patch import run_patch
from krom.stages.optimize import run_optimize
from krom.stages.wrap_up import run_wrap_up
from krom.stages.custom import run_custom

# Import enhancements (now with stubs, imports succeed)
from krom.enhancements.browser_cleanup import run_browser_cleanup
from krom.enhancements.privacy_scrub import run_privacy_scrub
from krom.enhancements.uninstall_residue import run_uninstall_residue
from krom.enhancements.driver_audit import run_driver_audit
from krom.enhancements.startup_manager import run_startup_manager
from krom.enhancements.benchmark_report import run_benchmark_report
from krom.enhancements.scheduled_mode import run_scheduled_mode
from krom.enhancements.hardware_health import run_hardware_health
from krom.enhancements.secure_wipe import run_secure_wipe

# Other imports
from krom.logger import setup_logging  # For centralized logging
from krom.utils.backup import restore_backup  # Now with stub
from krom.config import load_config  # Centralized config loading
from krom.utils.system import is_admin, run_as_admin  # For admin checks

# Define lists of stages and enhancements for multi-mode selection
all_stages = [
    'prep', 'temp_clean', 'de_bloat', 'disinfect',
    'repair', 'patch', 'optimize', 'wrap_up', 'custom'
]

all_enhancements = [
    'browser_cleanup', 'privacy_scrub', 'uninstall_residue', 'driver_audit',
    'startup_manager', 'benchmark_report', 'scheduled_mode', 'hardware_health', 'secure_wipe'
]

# All runners dict (stages + enhancements)
all_runners = {
    'prep': run_prep,
    'temp_clean': run_temp_clean,
    'de_bloat': run_de_bloat,
    'disinfect': run_disinfect,
    'repair': run_repair,
    'patch': run_patch,
    'optimize': run_optimize,
    'wrap_up': run_wrap_up,
    'custom': run_custom,
    'browser_cleanup': run_browser_cleanup,
    'privacy_scrub': run_privacy_scrub,
    'uninstall_residue': run_uninstall_residue,
    'driver_audit': run_driver_audit,
    'startup_manager': run_startup_manager,
    'benchmark_report': run_benchmark_report,
    'scheduled_mode': run_scheduled_mode,
    'hardware_health': run_hardware_health,
    'secure_wipe': run_secure_wipe,
}

def is_enabled(args: Namespace, config: dict, key: str, default: bool = False, category: str = None) -> bool:
    """Check if a stage/enhancement is enabled via args or config."""
    arg_value = getattr(args, key, None)
    if arg_value is not None:
        return arg_value
    if category:
        return config.get(category, {}).get(key, {}).get('enabled', default)
    return config.get('stages', {}).get(key, {}).get('enabled', default) if key in all_stages else config.get('enhancements', {}).get(key, {}).get('enabled', default)

def get_enabled_runners(args: Namespace, config: dict) -> list:
    """Get list of enabled runners based on args.selected or config defaults."""
    selected = getattr(args, 'selected', []) 
    if selected:
        return selected
    return [k for k in all_stages if is_enabled(args, config, k, category='stages')] + \
           [k for k in all_enhancements if is_enabled(args, config, k, category='enhancements')]

def print_intro():
    """Display the KROM ASCII art and welcome message."""
    ascii_art = r"""
           _   ________ ________  ___
          | | / /| ___ \  _  |  \/  |
          | |/ / | |_/ / | | | .  . |
          |    \ |    /| | | | |\/| |
          | |\  \| |\ \\ \_/ / |  | |
          \_| \_/\_| \_|\___/\_|  |_/

    A Python-based Windows Deep Cleaning Tool

                 Remember Tron.
    """
    print(ascii_art)

def print_wizard_help(config: dict):
    """Display wizard instructions, available commands, stages, enhancements, and flags."""
    print("\nWizard Navigation Commands (type at any prompt):")
    print("  - help: Display this wizard instructions and available commands.")
    print("  - back: Return to the previous question (redo your answer; limited to one step back for simplicity).")
    print("  - end: Quit the wizard and exit Krom without running.")
    print("  - start: Skip remaining prompts and begin the run with current selections (defaults for unanswered questions).")
    print("Press Enter at a prompt to use the default (shown in parentheses, e.g., (default: n)).")
    print("If you misanswer, use 'back' to correct without restarting. The wizard saves progress until you exit or start.\n")

    print("Available Stages (from config; * = enabled):")
    for name in all_stages:
        enabled = is_enabled(Namespace(), config, name, category='stages')
        print(f"  - {name}{' *' if enabled else ''}")

    print("\nAvailable Enhancements (from config; * = enabled):")
    for name in all_enhancements:
        enabled = is_enabled(Namespace(), config, name, category='enhancements')
        print(f"  - {name}{' *' if enabled else ''}")

    print("\nGlobal Flags (prompted in wizard or use via CLI):")
    print("  --verbose: Enable detailed logs")
    print("  --dry-run: Simulate actions without changes")
    print("  --no-backup: Skip backups")
    print("  --safe-mode: Prep for safe mode reboot")
    print("  --offline: Offline mode (no downloads/network)")
    print("For full CLI details, run with --help outside wizard.\n")

def get_user_input(prompt, default=None):
    """Helper to get input with special command check. Returns special strings for commands."""
    while True:
        if default:
            prompt = f"{prompt} (default: {default}): "
        user_input = input(prompt).strip().lower()
        if user_input in ['help', 'back', 'end', 'start']:
            return user_input
        return user_input or default

def graceful_exit():
    """Helper for consistent exit with prompt."""
    print("Exiting Krom...")
    input("Press Enter to exit.")
    sys.exit(0)

def interactive_mode(parser: ArgumentParser, config: dict):
    """Interactive wizard for non-CLI users: Prompt for flags and build args, using config as defaults."""
    print("=== Krom Quick Setup Wizard ===")
    print("Guide through options, or type 'help' for wizard commands.\n")

    # Initial prompt loop for start/help
    while True:
        user_input = get_user_input("Enter command (or 'start' to begin)")
        if user_input == 'help':
            print_wizard_help(config)
            continue
        elif user_input == 'end':
            graceful_exit()
        elif user_input in ['start', '']:
            break
        else:
            print("Type 'help' or press Enter to start.")

    args_dict = {}
    previous_responses = []  # For basic 'back' support

    def prompt_and_store(key, prompt_text, default='n'):
        while True:
            response = get_user_input(prompt_text, default=default)
            if response == 'help':
                print_wizard_help(config)
                continue
            elif response == 'end':
                graceful_exit()
            elif response == 'start':
                return 'start'  # Signal to start early
            elif response == 'back' and previous_responses:
                # Basic back: Redo last prompt
                previous_responses.pop()
                return prompt_and_store(*previous_responses[-1]) if previous_responses else response
            previous_responses.append((key, prompt_text, default))
            return response == 'y'

    # Global flags
    verbose = prompt_and_store('verbose', "Enable detailed logs? (y/n)", default='n')
    if verbose == 'start': return build_args(args_dict, config)
    args_dict['verbose'] = verbose
    dry_run = prompt_and_store('dry_run', "Dry run only (no changes)? (y/n)", default='n')
    if dry_run == 'start': return build_args(args_dict, config)
    args_dict['dry_run'] = dry_run
    no_backup = prompt_and_store('no_backup', "Skip backups? (y/n)", default='n')
    if no_backup == 'start': return build_args(args_dict, config)
    args_dict['no_backup'] = no_backup
    safe_mode = prompt_and_store('safe_mode', "Prep for safe mode? (y/n)", default='n')
    if safe_mode == 'start': return build_args(args_dict, config)
    args_dict['safe_mode'] = safe_mode
    offline = prompt_and_store('offline', "Offline mode (no network)? (y/n)", default='n')
    if offline == 'start': return build_args(args_dict, config)
    args_dict['offline'] = offline

    # Stages/enhancements selection
    mode = get_user_input("Run a single stage/enhancement (standalone; note: some may require multi mode) or select multiple (multi)? (standalone/multi)", default='multi')
    while mode in ['help', 'end', 'start', 'back']:
        if mode == 'help':
            print_wizard_help(config)
        elif mode == 'end':
            graceful_exit()
        elif mode == 'start':
            return build_args(args_dict, config)
        elif mode == 'back' and previous_responses:
            previous_responses.pop()
            # Redo last global prompt
            offline = prompt_and_store('offline', "Offline mode (no network)? (y/n)", default='n')
            args_dict['offline'] = offline
        mode = get_user_input("Run a single stage/enhancement (standalone; note: some may require multi mode) or select multiple (multi)? (standalone/multi)", default='multi')

    selected = []
    if mode == 'standalone':
        while True:
            name = get_user_input("Enter stage or enhancement name (e.g., 'prep' or 'browser_cleanup')").lower().replace('-', '_')
            if name in ['help', 'end', 'start', 'back']:
                if name == 'help':
                    print_wizard_help(config)
                    continue
                elif name == 'end':
                    graceful_exit()
                elif name == 'start':
                    return build_args(args_dict, config)
                elif name == 'back':
                    return interactive_mode(parser, config)  # Restart from mode
            if name in all_runners:
                func = all_runners[name]
                params = list(inspect.signature(func).parameters.keys())
                if len(params) < 3:
                    warn_resp = get_user_input(f"Warning: {name} uses legacy 2-arg mode (config, logger only). May ignore some CLI flags. Proceed? (y/n)", default='y')
                    if warn_resp in ['help', 'end', 'start', 'back']:
                        if warn_resp == 'help':
                            print_wizard_help(config)
                            continue
                        elif warn_resp == 'end':
                            graceful_exit()
                        elif warn_resp == 'start':
                            return build_args(args_dict, config)
                        elif warn_resp == 'back':
                            continue  # Redo name input
                    if warn_resp != 'y':
                        continue
                selected = [name]
                break
            else:
                print(f"Unknown: {name}. Try again or 'help' for list.")
    else:
        # Multi: List with * for config-enabled, then prompt to customize
        print("\nStages (from config):")
        for name in all_stages:
            enabled = is_enabled(Namespace(), config, name, category='stages')
            print(f"  - {name}{' *' if enabled else ''}")
        print("\nEnhancements (from config):")
        for name in all_enhancements:
            enabled = is_enabled(Namespace(), config, name, category='enhancements')
            print(f"  - {name}{' *' if enabled else ''}")
        customize = get_user_input("\nUse config defaults or customize selections? (defaults/custom)", default='defaults')
        while customize in ['help', 'end', 'start', 'back']:
            if customize == 'help':
                print_wizard_help(config)
            elif customize == 'end':
                graceful_exit()
            elif customize == 'start':
                return build_args(args_dict, config)
            elif customize == 'back':
                return interactive_mode(parser, config)
            customize = get_user_input("Use config defaults or customize selections? (defaults/custom)", default='defaults')
        if customize == 'custom':
            print("Customize: For each, enter 'y' to enable, 'n' to disable, or default to config.")
            for name in all_stages + all_enhancements:
                default_val = 'y' if is_enabled(Namespace(), config, name, category='stages' if name in all_stages else 'enhancements') else 'n'
                enable = prompt_and_store(name, f"Enable {name}? (y/n)", default=default_val)
                if enable == 'start':
                    return build_args(args_dict, config)
                if enable:
                    selected.append(name)
        else:
            selected = get_enabled_runners(Namespace(**args_dict), config)

    # Summary and confirm
    print("\n=== Summary ===")
    print(f"Globals: Dry-run: {args_dict.get('dry_run', False)}, Verbose: {args_dict.get('verbose', False)}, Offline: {args_dict.get('offline', False)}, No-backup: {args_dict.get('no_backup', False)}, Safe-mode: {args_dict.get('safe_mode', False)}")
    print(f"Selected: {', '.join(selected) or 'All defaults'}")
    confirm = get_user_input("Looks good? Run now? (y/n)", default='y')
    while confirm in ['help', 'back', 'end', 'start']:
        if confirm == 'help':
            print_wizard_help(config)
        elif confirm == 'end':
            graceful_exit()
        elif confirm == 'start' or confirm == 'y':
            break
        elif confirm == 'back':
            return interactive_mode(parser, config)
        confirm = get_user_input("Looks good? Run now? (y/n)", default='y')
    if confirm != 'y':
        graceful_exit()

    # Convert dict to Namespace
    args = Namespace(**args_dict)
    args.standalone = selected[0] if mode == 'standalone' and selected else None
    args.selected = selected if mode != 'standalone' else []

    return args

def build_args(args_dict: dict, config: dict):
    """Stub to build args early on 'start' (use defaults for unanswered)."""
    args = Namespace(**args_dict)
    args.standalone = None
    args.selected = get_enabled_runners(args, config)
    return args

def run_stages(args: Namespace, config: dict, logger: logging.Logger):
    """Run all or selected stages/enhancements in sequence."""
    selected = get_enabled_runners(args, config)
    if not selected:
        logger.warning("No stages/enhancements selected or enabled. Exiting.")
        return

    if 'benchmark_report' in selected:
        args.initial_disk_usage = {p.device: shutil.disk_usage(p.mountpoint).free for p in psutil.disk_partitions()}

    legacy_used = set()
    for name in tqdm(selected, desc="Running Stages/Enhancements", disable=not args.verbose):
        func = all_runners.get(name)
        if func:
            logger.info(f"Running: {name}")
            try:
                func(args, config, logger)
            except TypeError as e:
                if "takes 2 positional arguments but 3 were given" in str(e):
                    logger.warning(f"Signature mismatch for {name}; using legacy 2-arg mode. Update recommended.")
                    try:
                        func(config, logger)
                        legacy_used.add(name)
                    except Exception as inner_e:
                        logger.error(f"Failed legacy call for {name}: {inner_e}")
                else:
                    logger.error(f"Error running {name}: {e}")
        else:
            logger.warning(f"Unknown runner: {name}")

    if legacy_used:
        logger.warning(f"Legacy runners used: {', '.join(legacy_used)}. Update to 3-arg signature recommended.")

def main():
    """Main entry point: Parse args, load config, setup logger, run stages."""
    parser = ArgumentParser(description="Krom: Windows Deep Cleaning Tool")

    # Global flags
    parser.add_argument('--config', type=str, default='configs/default.yaml', help='Path to config YAML')
    parser.add_argument('--verbose', action='store_true', help='Enable detailed logs')
    parser.add_argument('--dry-run', action='store_true', help='Simulate actions without changes')
    parser.add_argument('--no-backup', action='store_true', help='Skip backups')
    parser.add_argument('--safe-mode', action='store_true', help='Prep for safe mode reboot')
    parser.add_argument('--offline', action='store_true', help='Offline mode (no downloads/network)')

    # Stage-specific params
    stages_group = parser.add_argument_group('Stage Params')
    stages_group.add_argument('--temp-dirs', nargs='+', help='Custom temp dirs for temp_clean')
    stages_group.add_argument('--bloat-list', type=str, help='Custom bloatware list file for de_bloat')
    stages_group.add_argument('--scan-tool', type=str, help='Scan tool for disinfect (e.g., clamav)')
    stages_group.add_argument('--offline-patches', type=str, help='Dir for bundled patches in patch')
    stages_group.add_argument('--plugins-dir', type=str, default='./plugins', help='Dir for custom plugins')

    # Enhancement flags (disabled by default, no no-flags)
    enhancements_group = parser.add_argument_group('Enhancement Flags')
    enhancements = ['browser_cleanup', 'privacy_scrub', 'uninstall_residue', 'driver_audit',
                    'startup_manager', 'benchmark_report', 'scheduled_mode', 'hardware_health', 'secure_wipe']
    for enh in enhancements:
        enhancements_group.add_argument(f'--{enh}', action='store_true', help=f'Enable {enh} enhancement')

    # Custom enhancement params
    enhancements_group.add_argument('--browsers', nargs='+', help='Browsers to target in browser_cleanup')
    enhancements_group.add_argument('--hosts-file', type=str, help='Custom hosts file for privacy_scrub')
    enhancements_group.add_argument('--suggest-updates', action='store_true', help='Suggest driver updates in driver_audit')
    enhancements_group.add_argument('--interactive', action='store_true', help='Interactive mode for startup_manager')
    enhancements_group.add_argument('--visualize', action='store_true', help='Visualize charts in benchmark_report')
    enhancements_group.add_argument('--frequency', type=str, help='Frequency for scheduled_mode (weekly/daily)')
    enhancements_group.add_argument('--wipe-paths', nargs='+', help='Paths for secure_wipe')

    # Standalone mode
    parser.add_argument('--standalone', type=str, help='Run only a specific stage/enhancement (e.g., hardware-health)')

    # Parse args
    args = parser.parse_args()

    # Load config early
    config = load_config(args.config)

    # If no args beyond script name, show intro and go interactive
    if len(sys.argv) == 1:
        print_intro()
        args = interactive_mode(parser, config)

    # Setup logger after config/args (for log path, etc.)
    logger = setup_logging(args.verbose, args.dry_run, config)  # Pass config for log path

    # Admin check
    if not is_admin():
        run_as_admin(logger)  # Warns or relaunches (stubbed)

    # Validation/conflicts
    if args.dry_run and not args.verbose:
        logger.warning("Dry-run enabled; consider --verbose for details.")
    if args.safe_mode and not is_admin():
        logger.warning("--safe-mode requires admin privileges; may fail.")

    if args.standalone:
        standalone_name = args.standalone.lower().replace('-', '_')
        if standalone_name in ['hardware', 'standalone_hardware']:
            standalone_name = 'hardware_health'
        elif standalone_name in ['wipe', 'standalone_wipe']:
            standalone_name = 'secure_wipe'
        func = all_runners.get(standalone_name)
        if func:
            logger.info(f"Running standalone: {standalone_name}")
            try:
                func(args, config, logger)
            except TypeError as e:
                if "takes 2 positional arguments but 3 were given" in str(e):
                    logger.warning(f"Signature mismatch for {standalone_name}; using legacy 2-arg mode. Update recommended.")
                    try:
                        func(config, logger)
                    except Exception as inner_e:
                        logger.error(f"Failed legacy call for {standalone_name}: {inner_e}")
                else:
                    logger.error(f"Error running {standalone_name}: {e}")
        else:
            logger.error(f"Unknown standalone: {args.standalone}")
            parser.print_help()
            sys.exit(1)
    else:
        run_stages(args, config, logger)

    input("Press Enter to exit.")  # Keeps console open

if __name__ == '__main__':
    main()