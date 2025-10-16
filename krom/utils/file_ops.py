import logging
import os
import shutil

def safe_delete(path: str, logger: logging.Logger, dry_run: bool = False) -> bool:
    if not os.path.exists(path):
        logger.debug(f"Path not found for deletion: {path}")
        return True
    if dry_run:
        logger.info(f"[Dry Run] Would delete: {path}")
        return True
    try:
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        logger.debug(f"Deleted: {path}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete {path}: {e}")
        return False