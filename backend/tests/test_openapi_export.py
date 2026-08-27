from __future__ import annotations

import json
from pathlib import Path

from option_arb.main import app
from option_arb.openapi import openapi_is_current, render_openapi, write_openapi


def test_openapi_export_is_stable_json_with_trailing_newline() -> None:
    rendered = render_openapi()

    assert rendered.endswith("\n")
    assert rendered == json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    assert json.loads(rendered)["openapi"].startswith("3.1.")


def test_openapi_snapshot_check(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "openapi.json"

    assert not openapi_is_current(output)
    write_openapi(output)
    assert openapi_is_current(output)

    output.write_text("{}\n", encoding="utf-8")
    assert not openapi_is_current(output)
