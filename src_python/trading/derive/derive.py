from __future__ import annotations


class DeriveAuth:
    pass


class DeriveOptionsTrader:
    def __init__(self, client_id: str, client_secret: str, testnet: bool = False) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://testnet.derive.com" if testnet else "https://api.derive.com"

    async def place_order(
        self,
        *,
        instrument_name: str,
        side: str,
        amount: float,
        price: float,
        order_type: str = "limit",
        time_in_force: str = "fill_or_kill",
    ) -> None:
        print("Derive orders: To implement")

