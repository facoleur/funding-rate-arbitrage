"""One-shot helper: given your Derive session key + EOA (or SCW address),
fetch and print your subaccount_id(s) via the private API.

Usage:
    cd backend
    uv run python scripts/derive_bootstrap.py \\
        --network testnet \\
        --session-key 0xYourSessionPrivateKey \\
        --wallet 0xYourDeriveSmartContractWallet

If you only have the EOA and not the SCW address yet, first check
https://app.derive.xyz/developers to copy the "Wallet" field.
"""
from __future__ import annotations

import argparse
import asyncio
import json

import httpx

from option_arb.exchanges import derive_constants
from option_arb.exchanges.derive_auth import DeriveAuth


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", choices=["mainnet", "testnet"], default="testnet")
    ap.add_argument("--session-key", required=True, help="Derive session key private key (0x…)")
    ap.add_argument("--wallet", required=True, help="Derive smart-contract wallet address (0x…)")
    args = ap.parse_args()

    constants = derive_constants.get(args.network)
    # subaccount_id=0 is a placeholder — /private/get_subaccounts doesn't need it
    auth = DeriveAuth(
        session_private_key=args.session_key,
        wallet_address=args.wallet,
        subaccount_id=0,
        constants=constants,
    )
    sig = await auth.sign_rest("POST", "/private/get_subaccounts", None)

    # Diagnostic info — printed even on error
    print(f"# network={args.network}  base_url={constants.rest_base_url}")
    print(f"# session signer address = {auth.signer_address}")
    print(f"# wallet (must be SCW, not EOA) = {auth.wallet_address}")
    print(f"# headers = {sig.headers}\n")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{constants.rest_base_url}/private/get_subaccounts",
            json={"wallet": args.wallet},
            headers=sig.headers,
        )
        print(f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except Exception:
            print("non-JSON body:", resp.text[:500])
            return

        print(json.dumps(data, indent=2))

        if resp.status_code >= 400:
            print("\nTroubleshooting:")
            print(f"  - signer_address ({auth.signer_address}) must be a REGISTERED")
            print(f"    session key on wallet {auth.wallet_address}.")
            print("  - wallet MUST be the Derive smart-contract wallet, NOT your EOA.")
            print("    Confirm on https://testnet.derive.xyz/developers → 'Wallet' field.")
            return

    result = data.get("result") or {}
    ids = result.get("subaccount_ids") or []
    if ids:
        print(f"\n→ Add to .env: DERIVE_SUBACCOUNT_ID={ids[0]}")
    else:
        print(
            "\nNo subaccounts found. Deposit USDC first on "
            f"{'app.derive.xyz' if args.network == 'mainnet' else 'testnet.derive.xyz'}"
            " to auto-create one."
        )


if __name__ == "__main__":
    asyncio.run(main())
