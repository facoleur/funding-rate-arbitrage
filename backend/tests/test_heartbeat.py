from __future__ import annotations

import time
from pathlib import Path

import option_arb.heartbeat as hb


def test_beat_writes_fresh_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(hb, "HEARTBEAT_DIR", tmp_path)
    hb.beat("screener")
    f = tmp_path / "hb_screener"
    assert f.exists()
    assert time.time() - f.stat().st_mtime < 5


def test_beat_swallows_io_error(tmp_path: Path, monkeypatch) -> None:
    # point at a path that cannot be created (parent is a file)
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    monkeypatch.setattr(hb, "HEARTBEAT_DIR", blocker / "nested")
    hb.beat("executor")  # must not raise
