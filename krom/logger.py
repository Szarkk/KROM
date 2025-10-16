import logging
import os
from pathlib import Path
from datetime import datetime

def setup_logging(verbose=False, dry_run=False, config=None):
    """
    Centralized logging setup: Console + file in logs/ dir.
    Configurable path via YAML; creates dir if needed.
    Generates a new log file each run named krom_YYYYMMDD_HHMMSS.log.
    """
    # Default log dir
    log_dir = Path(config.get('paths', {}).get('logs', 'logs')) if config else Path('logs')
    
    # Create logs dir if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique log filename with date/time
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'krom_{timestamp}.log'
    
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),  # Console output
            logging.FileHandler(log_file)  # Unique file per run
        ]
    )
    
    logger = logging.getLogger(__name__)
    if dry_run:
        logger.info("Dry run mode enabled: No changes will be made.")
    
    logger.info(f"Logging initialized to: {log_file}")
    return logger