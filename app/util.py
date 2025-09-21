"""
utility functions
"""

import sys
import os
import functools
import logging
import yaml  # type: ignore
from app.paths import CONFIG_YAML_PATH

logger = logging.getLogger(__name__)

@functools.lru_cache(maxsize=1)
def get_config():
    with open(CONFIG_YAML_PATH, 'r') as f:
        return yaml.safe_load(f)

@functools.lru_cache(maxsize=1)
def get_secrets():
    return get_config()['secrets']

def get_secret(category,name):
    """Get a secret value, checking environment variables first, then secrets file"""
    env_name = category.upper()+"_"+name.upper()
    if env_name in os.environ:
        return os.environ[env_name]
    try:
        return get_secrets()[category][name]
    except KeyError as e:
        logger.error("no secret [%s][%s] in %s",category,name,CONFIG_YAML_PATH)
        raise RuntimeError("no secret") from e
