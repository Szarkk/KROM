import logging
import os
import platform
import shutil
import psutil
import re
from pathlib import Path
from tqdm import tqdm  # For progress if verbose
from datetime import datetime  # For timestamp

def run_wrap_up(args, config, logger: logging.Logger, log_file: str = None):
    """
    Wrap-Up stage: Generate logs/reports and clean up.
    Based on KromFeaturesOverview.md and KromCLIOverview.md.
    """
    # Wrap-up is more cross-platform, so no strict OS skip
    if platform.system() != 'Windows':
        logger.warning("Wrap-Up stage: Some features may be limited on non-Windows.")

    dry_run = args.dry_run
    verbose = getattr(args, 'verbose', config.get('verbose', False))

    logger.info("Starting Wrap-Up stage...")

    # Define steps for progress (if verbose)
    steps = ["Generate Report", "Clean Up Artifacts", "Run Benchmark (if enabled)"]
    pbar = None
    if verbose and not dry_run:
        pbar = tqdm(steps, desc="Wrap-Up Progress", dynamic_ncols=True)

    # Step 1: Generate report (e.g., summarize logs)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = Path(f'krom_report_{timestamp}.txt')
    if dry_run:
        logger.info(f"[Dry Run] Would generate report: {report_file}")
    else:
        try:
            if not log_file:
                log_dir = Path(config.get('paths', {}).get('logs', 'logs'))
                log_files = list(log_dir.glob('krom_*.log'))
                if log_files:
                    log_file = max(log_files, key=os.path.getctime)  # Latest log
                    logger.info(f"Using latest log for summary: {log_file}")
                else:
                    log_file = None
            
            if log_file and Path(log_file).exists():
                with Path(log_file).open('r') as log_file_handle:
                    logs = log_file_handle.read()
            else:
                logs = ""
                logger.warning("No log file found; generating empty summary.")
            
            # Base summary: INFO/ERROR lines
            summary = "Krom Run Summary:\n" + "\n".join([line for line in logs.splitlines() if 'INFO' in line or 'ERROR' in line])
            
            # Enhanced: "What Was Done" by stage (parse with regex for stage prefixes and actions)
            stage_actions = {}
            current_stage = None
            for line in logs.splitlines():
                stage_match = re.search(r'Running stage: (\w+)', line)
                if stage_match:
                    current_stage = stage_match.group(1)
                    stage_actions.setdefault(current_stage, [])
                if any(keyword in line for keyword in ['Deleted', 'Removed', 'Cleaned', 'Disabled', 'Applied', 'Completed']):
                    if current_stage:
                        stage_actions[current_stage].append(line.strip())
            
            if stage_actions:
                summary += "\n\nWhat Was Done (By Stage):\n"
                for stage, actions in stage_actions.items():
                    summary += f"{stage.capitalize()}:\n" + "\n".join(actions[-10:]) + "\n"  # Last 10 per stage for brevity
            
            # Enhanced: Storage changes (if initial_disk_usage passed from main.py)
            if hasattr(args, 'initial_disk_usage'):
                summary += "\n\nStorage Changes:\n"
                for drive, initial_free in args.initial_disk_usage.items():
                    try:
                        current_free = shutil.disk_usage(drive).free
                        freed = (current_free - initial_free) / (1024 ** 3)  # GB
                        summary += f"{drive} - Freed: {freed:.2f} GB\n"
                    except Exception as e:
                        summary += f"{drive} - Could not calculate: {e}\n"

            report_file.write_text(summary)
            logger.info(f"Generated report: {report_file}")
            
            # Optional: Print console recap if verbose
            if verbose:
                print("\nQuick Recap (full in {report_file}):\n" + summary[:1000] + "...")  # Truncate for console
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
    
    if pbar: pbar.update(1)

    # Flush logs before cleanup (in case of failures)
    logger.handlers[1].flush()  # File handler

    # Step 2: Clean up tools/artifacts (e.g., delete temp backups if configured)
    cleanup_paths = [Path(p) for p in config.get('cleanup_paths', [])]  # e.g., ['./temp_tools']
    for path in cleanup_paths:
        if path.exists():
            if dry_run:
                logger.info(f"[Dry Run] Would clean up: {path}")
            else:
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    logger.info(f"Cleaned up: {path}")
                except Exception as e:
                    logger.error(f"Failed to clean up {path}: {e}")
    
    if pbar: pbar.update(1)

    # Step 3: Hook for enhancements like benchmark_report if enabled
    if getattr(args, 'benchmark_report', False) or config.get('enhancements', {}).get('benchmark_report', False):
        logger.info("Benchmark & Report enhancement enabled; generating before/after report.")
        # Call from enhancements/benchmark_report.py if implemented
        # e.g., from krom.enhancements.benchmark_report import run_benchmark_report
        # run_benchmark_report(args, config, logger)
        # Enhanced Placeholder: Use psutil for metrics from config.enhancements.benchmark_report.metrics
        metrics = config.get('enhancements', {}).get('benchmark_report', {}).get('metrics', ['cpu', 'memory', 'disk'])
        if not dry_run:
            try:
                benchmark_summary = "\nPost-Run Benchmarks:"
                if 'cpu' in metrics:
                    benchmark_summary += f"\nCPU Usage: {psutil.cpu_percent()}%"
                if 'memory' in metrics:
                    benchmark_summary += f"\nMemory Usage: {psutil.virtual_memory().percent}%"
                if 'disk' in metrics:
                    benchmark_summary += f"\nDisk Usage (C:): {psutil.disk_usage('C:').percent}%"
                # Add more (e.g., network: psutil.net_io_counters())
                with report_file.open('a') as f:
                    f.write(benchmark_summary)
                logger.info("Appended benchmark to report.")
            except Exception as e:
                logger.error(f"Failed to run benchmark: {e}")
    
    if pbar: 
        pbar.update(1)
        pbar.close()

    logger.info("Wrap-Up stage completed. Krom run finished.")