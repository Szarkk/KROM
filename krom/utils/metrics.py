import logging
import psutil

def get_system_metrics(logger: logging.Logger) -> dict:
    try:
        return {
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': {p.device: psutil.disk_usage(p.mountpoint).percent for p in psutil.disk_partitions()}
        }
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        return {}