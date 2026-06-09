from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def format_table(rows: Iterable[dict[str, Any]], headers: list[str] | None = None) -> str:
    rows = list(rows)
    if not rows:
        return ""

    columns = headers or list(rows[0].keys())
    values = [[str(row.get(col, "")) for col in columns] for row in rows]
    widths = [
        max(len(str(col)), *(len(row[index]) for row in values))
        for index, col in enumerate(columns)
    ]

    header = "  ".join(str(col).ljust(widths[index]) for index, col in enumerate(columns))
    divider = "  ".join("-" * width for width in widths)
    body = "\n".join(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in values
    )
    return f"{header}\n{divider}\n{body}"
