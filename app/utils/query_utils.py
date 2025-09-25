"""
Query-related utility functions
"""
from flask import request


def temporal_quantification(cmd, args):
    """Annotate cmd and args with start, end, limit"""
    start = request.args.get("start", type=int)
    end = request.args.get("end", type=int)

    if start is not None:
        cmd += " AND logtime >= ? "
        args.append(start)

    if end is not None:
        cmd += " AND logtime <= ? "
        args.append(end)

    return (cmd, args)
