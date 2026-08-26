"""Derive (Lyra V2) protocol constants — source: docs.derive.xyz/docs/protocol-constants.

These are load-bearing for order signing. If a value is wrong, orders
either reject with a signature error or execute against the wrong module.
Verify against docs.derive.xyz whenever the protocol upgrades."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Network = Literal["mainnet", "testnet"]


@dataclass(frozen=True)
class DeriveConstants:
    network: Network
    chain_id: int
    domain_separator: str
    action_typehash: str
    matching_contract: str
    trade_module: str
    deposit_module: str
    withdraw_module: str
    usdc_asset: str
    rest_base_url: str
    ws_url: str


MAINNET = DeriveConstants(
    network="mainnet",
    chain_id=957,
    domain_separator="0xd96e5f90797da7ec8dc4e276260c7f3f87fedf68775fbe1ef116e996fc60441b",
    action_typehash="0x4d7a9f27c403ff9c0f19bce61d76d82f9aa29f8d6d4b0c5474607d9770d1af17",
    matching_contract="0xeB8d770ec18DB98Db922E9D83260A585b9F0DeAD",
    trade_module="0xB8D20c2B7a1Ad2EE33Bc50eF10876eD3035b5e7b",
    deposit_module="0x9B3FE5E5a3bcEa5df4E08c41Ce89C4e3Ff01Ace3",
    withdraw_module="0x9d0E8f5b25384C7310CB8C6aE32C8fbeb645d083",
    usdc_asset="0x6879287835A86F50f784313dBEd5E5cCC5bb8481",
    rest_base_url="https://api.lyra.finance",
    ws_url="wss://api.lyra.finance/ws",
)


TESTNET = DeriveConstants(
    network="testnet",
    chain_id=901,
    domain_separator="0x9bcf4dc06df5d8bf23af818d5716491b995020f377d3b7b64c29ed14e3dd1105",
    action_typehash="0x4d7a9f27c403ff9c0f19bce61d76d82f9aa29f8d6d4b0c5474607d9770d1af17",
    matching_contract="0x3cc154e220c2197c5337b7Bd13363DD127Bc0C6E",
    trade_module="0x87F2863866D85E3192a35A73b388BD625D83f2be",
    deposit_module="0x43223Db33AdA0575D2E100829543f8B04A37a1ec",
    withdraw_module="0xe850641C5207dc5E9423fB15f89ae6031A05fd92",
    usdc_asset="0xe80F2a02398BBf1ab2C9cc52caD1978159c215BD",
    rest_base_url="https://api-demo.lyra.finance",
    ws_url="wss://api-demo.lyra.finance/ws",
)


def get(network: Network) -> DeriveConstants:
    return MAINNET if network == "mainnet" else TESTNET
