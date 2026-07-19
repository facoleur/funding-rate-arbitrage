from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal

_MONTHS = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}

_DERIBIT_RE = re.compile(r"^([A-Z]+)-(\d{1,2})([A-Z]{3})(\d{2})-(\d+)-(C|P)$")


def normalize_deribit(instrument: str) -> str:
    """`BTC-25OCT25-30000-C` -> `BTC-20251025-30000-C`."""
    m = _DERIBIT_RE.match(instrument)
    if not m:
        raise ValueError(f"invalid deribit instrument format: {instrument}")
    coin, day, mon_str, year_short, strike, side = m.groups()
    mon = _MONTHS.get(mon_str.upper())
    if not mon:
        raise ValueError(f"invalid month in {instrument}")
    return f"{coin}-20{year_short}{mon}{day.zfill(2)}-{strike}-{side}"


def normalize_from_parts(
    underlying: str, expiry: datetime, strike: Decimal, option_type: str
) -> str:
    """Build the canonical normalized name from parts."""
    if option_type not in ("C", "P"):
        raise ValueError(f"option_type must be C or P, got {option_type}")
    exp_utc = expiry.astimezone(UTC) if expiry.tzinfo else expiry
    date_str = exp_utc.strftime("%Y%m%d")
    strike_str = format(strike.normalize(), "f").rstrip("0").rstrip(".")
    if "." not in strike_str:
        # keep as integer if strike is whole
        strike_str = str(int(strike))
    return f"{underlying}-{date_str}-{strike_str}-{option_type}"
