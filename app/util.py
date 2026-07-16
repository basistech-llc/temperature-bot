"""
utility functions
"""

import time
import os
import functools
import logging
import yaml

from app.paths import CONFIG_YAML_PATH

logger = logging.getLogger(__name__)
TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


def env_flag_enabled(name: str) -> bool:
    """Return whether an environment flag contains an explicit true value."""
    return os.getenv(name, "").strip().lower() in TRUE_ENV_VALUES


@functools.lru_cache(maxsize=1)
def get_config():
    try:
        with CONFIG_YAML_PATH.open('r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("File not found: %s",CONFIG_YAML_PATH)
        raise

@functools.lru_cache(maxsize=1)
def get_secrets():
    return get_config()['secrets']

def get_secret(category,name):
    """Get a secret value, checking environment variables first, then secrets file"""
    logger.debug("get_secret(%s,%s)",category,name)
    env_name = category.upper()+"_"+name.upper()
    if env_name in os.environ:
        logger.debug("SECRET (%s,%s) from environment %s",category,name,env_name)
        return os.environ[env_name]
    try:
        return get_secrets()[category][name]
    except KeyError as e:
        logger.error("no secret [%s][%s] in %s",category,name,CONFIG_YAML_PATH)
        raise RuntimeError("no secret") from e

def github_style_duration(past_time, now=None):
    """Convert time difference to GitHub-style duration string"""
    if now is None:
        now = time.time()
    seconds = int(now - past_time)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    if days < 30:
        return f"{days}d"
    months = days // 30
    if months < 12:
        return f"{months}mo"
    years = months // 12
    return f"{years}y"
