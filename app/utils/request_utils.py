"""
Request utility functions for parsing common request parameters.
"""
from typing import List, Optional
from flask import request


def parse_device_ids() -> Optional[List[int]]:
    """Parse device_ids parameter from request args."""
    device_ids_param = request.args.get("device_ids", "")

    if not device_ids_param:
        return None

    try:
        return [
            int(did.strip()) for did in device_ids_param.split(",") if did.strip()
        ]
    except ValueError:
        return None
