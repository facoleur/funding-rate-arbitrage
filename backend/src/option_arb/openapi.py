from __future__ import annotations

import argparse
import json
from pathlib import Path

from option_arb.main import app


def render_openapi() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def write_openapi(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_openapi(), encoding="utf-8")


def openapi_is_current(output: Path) -> bool:
    return output.exists() and output.read_text(encoding="utf-8") == render_openapi()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the option-arb OpenAPI schema")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="Fail if the output is stale")
    args = parser.parse_args()

    if args.check:
        if not openapi_is_current(args.output):
            parser.exit(
                1, f"OpenAPI contract is stale: {args.output}\nRun: make contract-generate\n"
            )
        print("OpenAPI contract is current.")
        return

    write_openapi(args.output)


if __name__ == "__main__":
    main()
