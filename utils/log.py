"""Minimal logging helpers.

The bot's diagnostics are verbose by design (calibration is hard to debug
otherwise), so they go through `debug()` and can be silenced by setting
`config.DEBUG = False` or the env var `CP_BOT_DEBUG=0`.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

_ENV = os.environ.get("CP_BOT_DEBUG")


def debug_enabled() -> bool:
    if _ENV is not None:
        return _ENV not in ("0", "false", "False", "")
    return bool(getattr(config, "DEBUG", False))


def debug(msg: str):
    """Print a diagnostic message when debugging is enabled."""
    if debug_enabled():
        print(msg)


def info(msg: str):
    """Print a message that is always relevant to the user."""
    print(msg)
