"""
utility functions
"""

import sys
import os
import functools
import yaml  # type: ignore
from app.paths import CONFIG_YAML_PATH


@functools.lru_cache(maxsize=1)
def get_config():
    with open(CONFIG_YAML_PATH, 'r') as f:
        return yaml.safe_load(f)

@functools.lru_cache(maxsize=1)
def get_secrets():
    return get_config()['secrets']

def get_secret(category,name):
    """Get a secret value, checking environment variables first, then secrets file"""
    print("get_secrets()=",get_secrets(),file=sys.stderr)
    env_name = category.upper()+"_"+name.upper()
    if env_name in os.environ:
        return os.environ[env_name]
    try:
        return get_secrets()[category][name]
    except KeyError:
        logger.debug("secrets=%s",get_secrets())
        raise
