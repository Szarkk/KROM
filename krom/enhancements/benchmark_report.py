"""
benchmark_report.py

Enhancement module for Krom: Runs before/after performance benchmarks (CPU, memory, disk, network)
and generates visualizations/reports to show improvements.

Associated with: Wrap-Up stage.
CLI Flags: --benchmark-report (enable), --metrics <cpu,memory>.

Exports: run_benchmark_report(config: dict, logger: logging.Logger) -> None
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, List

import psutil

# Optional: For network (add 'speedtest-cli' to requirements.txt)
try:
    import speedtest  # type: ignore
except ImportError:
    speedtest = None

# Optional: For visualization (add 'matplotlib' to requirements.txt)
try:
    import matplotlib.pyplot as plt  # type: ignore
except ImportError:
    plt = None

def run_benchmark_report(config: Dict[str, Any], logger: logging.Logger) -> None:
    """
    Run the benchmark & report enhancement.

    Args:
        config (Dict[str, Any]): Configuration dictionary.
        logger (logging.Logger): Logger instance for output.

    Returns:
        None

    Example:
        config = {
            'enhancements': {'benchmark_report': {'enabled': True, 'metrics': ['cpu', 'disk'], 'pre_post': True, 'visualize': False}},
            'dry_run': False,
            'offline': False,
            'paths': {'temp_dir': './temp'}
        }
        run_benchmark_report(config, logger)
    """
    start_time = time.time()
    logger.info("=== Starting Benchmark & Report ===")
    
    # Load config for benchmark_report with safe gets
    enhancements = config.get('enhancements', {})
    br_config = enhancements.get('benchmark_report', {})
    enabled = br_config.get('enabled', False)
    if not enabled:
        logger.info("Benchmark report not enabled; skipping.")
        return
    
    metrics = br_config.get('metrics', ['cpu', 'memory', 'disk', 'network'])
    visualize = br_config.get('visualize', True)
    pre_post = br_config.get('pre_post', True)
    report_path = Path(br_config.get('report_path', './logs/benchmark_report.txt'))
    dry_run = config.get('dry_run', False)
    offline = config.get('offline', False)
    
    if 'network' in metrics and (offline or speedtest is None):
        logger.warning("Network metric skipped: Offline mode or speedtest-cli not available.")
        metrics = [m for m in metrics if m != 'network']
    
    if visualize and plt is None:
        logger.warning("Visualization disabled: matplotlib not available.")
        visualize = False
    
    # Dry-run simulation
    if dry_run:
        logger.info("Dry-run mode: Simulating benchmarks without real tests.")
        metric_key_map = {
            'cpu': ['cpu_usage_percent'],
            'memory': ['memory_usage_percent'],
            'disk': ['disk_write_mb_s', 'disk_read_mb_s'],
            'network': ['download_mbps', 'upload_mbps']
        }
        simulated_before = {}
        simulated_after = {}
        for m in metrics:
            keys = metric_key_map.get(m, [])
            for key in keys:
                base_val = 50.0 if 'usage' in key else 100.0  # Lower for usage, higher for speeds
                simulated_before[key] = base_val
                # Simulate improvement: reduce for usage, increase for speeds
                simulated_after[key] = base_val * 0.8 if 'usage' in key else base_val * 1.2
        _generate_report(simulated_before, simulated_after, report_path, visualize, config, logger)
        logger.debug(f"Benchmark report completed in {time.time() - start_time:.2f} seconds.")
        return
    
    # Pre-metrics if enabled
    before = {}
    if pre_post:
        logger.info("Collecting pre-Krom benchmarks...")
        before = _collect_metrics(metrics, config, logger)
    
    # Placeholder: Main Krom stages would run here in main.py orchestration; for standalone, assume post-only or simulate
    
    # Post-metrics
    logger.info("Collecting post-Krom benchmarks...")
    after = _collect_metrics(metrics, config, logger)
    
    # Generate report and visuals
    _generate_report(before, after, report_path, visualize, config, logger)
    
    logger.info("=== Benchmark & Report Completed ===")
    logger.debug(f"Benchmark report completed in {time.time() - start_time:.2f} seconds.")

def _collect_metrics(enabled_metrics: List[str], config: Dict[str, Any], logger: logging.Logger) -> Dict[str, float]:
    """Collect system metrics."""
    results = {}
    
    if 'cpu' in enabled_metrics:
        # CPU percent over 1s interval
        results['cpu_usage_percent'] = psutil.cpu_percent(interval=1)
        logger.debug(f"CPU usage: {results['cpu_usage_percent']}%")
    
    if 'memory' in enabled_metrics:
        # Memory usage percent
        results['memory_usage_percent'] = psutil.virtual_memory().percent
        logger.debug(f"Memory usage: {results['memory_usage_percent']}%")
    
    if 'disk' in enabled_metrics:
        # Disk read/write speed test (simple temp file; MB/s)
        temp_dir = Path(config.get('paths', {}).get('temp_dir', './temp'))
        temp_dir.mkdir(exist_ok=True)
        temp_file = temp_dir / 'temp_benchmark.bin'
        size_mb = 50  # Reduced to 50 MB for faster tests; configurable if needed
        data = os.urandom(size_mb * 1024 * 1024)
        
        try:
            # Write test
            start = time.time()
            with open(temp_file, 'wb') as f:
                f.write(data)
            write_time = time.time() - start
            results['disk_write_mb_s'] = size_mb / write_time
            
            # Read test
            start = time.time()
            with open(temp_file, 'rb') as f:
                f.read()
            read_time = time.time() - start
            results['disk_read_mb_s'] = size_mb / read_time
            
            logger.debug(f"Disk write: {results['disk_write_mb_s']:.2f} MB/s, read: {results['disk_read_mb_s']:.2f} MB/s")
        except (OSError, PermissionError) as e:
            logger.warning(f"Disk benchmark failed: {str(e)}. Skipping disk metrics.")
        finally:
            if temp_file.exists():
                temp_file.unlink()
    
    if 'network' in enabled_metrics and speedtest:
        try:
            st = speedtest.Speedtest()
            st.get_best_server()
            results['download_mbps'] = st.download() / 1_000_000
            results['upload_mbps'] = st.upload() / 1_000_000
            logger.debug(f"Network download: {results['download_mbps']:.2f} Mbps, upload: {results['upload_mbps']:.2f} Mbps")
        except Exception as e:
            logger.warning(f"Network test failed: {str(e)}. Skipping network metrics.")
    
    return results

def _generate_report(before: Dict[str, float], after: Dict[str, float], report_path: Path, visualize: bool, config: Dict[str, Any], logger: logging.Logger) -> None:
    """Generate text report and optional visualizations."""
    report_path.parent.mkdir(exist_ok=True)
    logs_path = report_path.parent
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("Krom Benchmark Report\n")
        f.write("=" * 30 + "\n\n")
        if before:
            f.write("Before Krom:\n")
            for k, v in before.items():
                f.write(f"  {k}: {v:.2f}\n")
        f.write("\nAfter Krom:\n")
        for k, v in after.items():
            f.write(f"  {k}: {v:.2f}\n")
        if before:
            f.write("\nImprovements (positive = better):\n")
            for k in set(before) & set(after):
                is_lower_better = 'usage' in k  # Expand if needed for other lower-better metrics
                raw_delta = after[k] - before[k]
                improvement = -raw_delta if is_lower_better else raw_delta
                status = 'better' if improvement > 0 else 'worse' if improvement < 0 else 'no change'
                f.write(f"  {k} improvement: {improvement:.2f} ({status})\n")
    
    logger.info(f"Report saved to: {report_path}")
    
    if visualize:
        try:
            # Simple bar chart
            keys = list(set(before) | set(after))
            before_vals = [before.get(k, 0) for k in keys]
            after_vals = [after.get(k, 0) for k in keys]
            
            x = range(len(keys))
            width = 0.35
            fig, ax = plt.subplots()
            if before:
                ax.bar([i - width/2 for i in x], before_vals, width, label='Before')
            ax.bar([i + width/2 if before else i for i in x], after_vals, width, label='After')
            ax.set_ylabel('Value')
            ax.set_title('Krom Benchmark Before/After' if before else 'Krom Benchmark (Post-Only)')
            ax.set_xticks(x)
            ax.set_xticklabels(keys, rotation=45, ha='right')
            ax.legend()
            
            plt.tight_layout()
            chart_path = logs_path / 'benchmark_chart.png'
            plt.savefig(chart_path)
            plt.close()
            logger.info(f"Chart saved to: {chart_path}")
        except Exception as e:
            logger.warning(f"Visualization failed: {str(e)}. Falling back to text report.")