"""Liveness heartbeat: each long-running loop touches a file every iteration.

Docker healthchecks read the file mtime (`find -mmin -N`) to tell a *hung*
event loop apart from a healthy one — a plain PID check can't, since a hung
process is still PID 1. Best-effort: any I/O error is swallowed so the
heartbeat never takes down the caller.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)

HEARTBEAT_DIR = Path(os.environ.get("HEARTBEAT_DIR", "/tmp"))


def beat(name: str) -> None:
    try:
        HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
        (HEARTBEAT_DIR / f"hb_{name}").write_text(str(time.time()))
    except OSError as e:  # read-only fs, permissions, disk full — never fatal
        log.debug("heartbeat %s failed: %s", name, e)
