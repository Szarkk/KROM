import logging
import requests

def check_for_update(api_url: str, logger: logging.Logger) -> str:
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        return response.json().get('tag_name', 'unknown')
    except requests.RequestException as e:
        logger.error(f"Failed to check update at {api_url}: {e}")
        return 'unknown'