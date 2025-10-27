import logging
import os
import platform
import shutil
import psutil
import re
from pathlib import Path
from tqdm import tqdm  # For progress if verbose
from datetime import datetime  # For timestamp
from krom.utils.metrics import get_baseline_metrics, get_current_metrics  # For before/after

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

    try:  # Wrap entire function for safe tqdm close on errors
        # Step 1: Generate report (e.g., summarize logs)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_dir = Path(config.get('paths', {}).get('logs', 'logs'))
        log_dir.mkdir(exist_ok=True)  # Ensure logs dir exists
        report_file = log_dir / f'krom_report_{timestamp}.txt'  # Place in logs dir
        if dry_run:
            logger.info(f"[Dry Run] Would generate report: {report_file}")
        else:
            try:
                if not log_file:
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
                
                # Enhanced: Before/After Changes (using baselines from Prep)
                changes_section = ""
                if hasattr(args, 'baseline_metrics') and args.baseline_metrics:
                    current_metrics = get_current_metrics(config, logger)
                    changes_section = "\n\nBefore/After Changes:\n"
                    for key in args.baseline_metrics:
                        baseline = args.baseline_metrics.get(key, 0)
                        current = current_metrics.get(key, 0)
                        if key == 'disk_free_gb':
                            delta = current - baseline
                            pct = (delta / baseline * 100) if baseline else 0
                            changes_section += f"Disk Free: {baseline:.2f} GB → {current:.2f} GB ({delta:+.2f} GB, {pct:+.1f}%)\n"
                        elif key == 'temp_size_gb':
                            delta = baseline - current  # Freed = reduction
                            pct = (delta / baseline * 100) if baseline else 0
                            changes_section += f"Temp Files: {baseline:.2f} GB → {current:.2f} GB (Freed {delta:.2f} GB, {pct:.1f}%)\n"
                        elif key == 'startup_items':
                            delta = baseline - current  # Reduced = improvement
                            pct = (delta / baseline * 100) if baseline else 0
                            changes_section += f"Startup Items: {baseline} → {current} (Disabled {delta}, {pct:.1f}%)\n"
                        # Add more keys as needed
                    summary += changes_section

                report_file.write_text(summary)
                logger.info(f"Generated report: {report_file}")
                
                # Optional: Print console recap if verbose
                if verbose:
                    print(f"\nQuick Recap (full in {report_file}):\n" + summary[:1000] + "...")
                    if changes_section:
                        print("\nKey Changes:\n" + changes_section)
            except Exception as e:
                logger.error(f"Failed to generate report: {e}")
        
        if pbar: pbar.update(1)

        # Step 2: Clean up tools/artifacts (e.g., delete temp backups if configured)
        cleanup_paths = config.get('cleanup_paths', [])  # Default to empty list if missing
        for path_str in cleanup_paths:
            path = Path(path_str)
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
        
        if pbar: pbar.update(1)

    except Exception as e:
        logger.error(f"Unexpected error in Wrap-Up: {e}")
    finally:
        # Safe flush: Loop over all handlers instead of indexing
        try:
            for handler in logger.handlers:
                handler.flush()
        except Exception as flush_e:
            logger.warning(f"Logging flush incomplete: {flush_e}")
        # Ensure tqdm closes even on errors
        if pbar:
            pbar.close()

    logger.info("Wrap-Up stage completed. Krom run finished.")