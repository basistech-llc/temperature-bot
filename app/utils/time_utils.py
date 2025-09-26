"""
Time-related utility functions
"""
import time


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
