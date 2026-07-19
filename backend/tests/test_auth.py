from __future__ import annotations

import pytest

from option_arb.exchanges.auth import (
    AuthNotReadyError,
    DeribitOAuth,
    EIP712Auth,
    NoAuth,
    build_authenticator,
)


@pytest.mark.asyncio
async def test_no_auth_rejects_private_calls() -> None:
    auth = NoAuth()
    with pytest.raises(AuthNotReadyError):
        await auth.sign_rest("POST", "/private/buy", {})


@pytest.mark.asyncio
async def test_deribit_oauth_requires_credentials() -> None:
    with pytest.raises(ValueError):
        DeribitOAuth("", "")


@pytest.mark.asyncio
async def test_deribit_oauth_fetches_and_caches_token() -> None:
    calls: list[dict] = []

    async def fake_auth(params: dict) -> dict:
        calls.append(params)
        return {"access_token": "tok_" + str(len(calls)), "expires_in": 900}

    auth = DeribitOAuth("id", "secret", auth_call=fake_auth)
    sig1 = await auth.sign_rest("POST", "/private/buy", {})
    sig2 = await auth.sign_rest("POST", "/private/sell", {})

    assert sig1.headers["Authorization"] == "Bearer tok_1"
    assert sig2.headers["Authorization"] == "Bearer tok_1"  # cached
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_deribit_oauth_ws_message_injects_token() -> None:
    async def fake_auth(params: dict) -> dict:
        return {"access_token": "abc", "expires_in": 900}

    auth = DeribitOAuth("id", "secret", auth_call=fake_auth)
    out = await auth.sign_ws_message({"method": "private/cancel", "params": {"order_id": "x"}})
    assert out["params"]["access_token"] == "abc"


def test_eip712_auth_requires_key() -> None:
    with pytest.raises(ValueError):
        EIP712Auth(
            session_private_key="",
            wallet_address="0x1",
            chain_id=1,
            domain_name="X",
            verifying_contract="0x0",
        )


def test_eip712_auth_signer_address_matches_key() -> None:
    from eth_account import Account

    acc = Account.create()
    auth = EIP712Auth(
        session_private_key=acc.key.hex(),
        wallet_address=acc.address,
        chain_id=957,
        domain_name="Matching",
        verifying_contract="0x0000000000000000000000000000000000000000",
    )
    assert auth.signer_address.lower() == acc.address.lower()


def _empty_settings():
    """Settings ignores .env — use for tests that check missing-creds paths.
    We can't use Settings() because pydantic-settings would load the real
    .env file if present in the CWD."""
    from types import SimpleNamespace

    return SimpleNamespace(
        deribit_client_id="",
        deribit_client_secret="",
        derive_wallet_address="",
        derive_subaccount_id=0,
        derive_session_private_key="",
        aevo_wallet_address="",
        aevo_signing_key="",
    )


def test_build_authenticator_returns_noauth_when_creds_missing() -> None:
    s = _empty_settings()
    assert isinstance(build_authenticator("deribit", s), NoAuth)
    assert isinstance(build_authenticator("derive", s), NoAuth)
    assert isinstance(build_authenticator("aevo", s), NoAuth)


def test_build_authenticator_returns_deribit_oauth_when_creds_set() -> None:
    s = _empty_settings()
    s.deribit_client_id = "id"
    s.deribit_client_secret = "sec"
    a = build_authenticator("deribit", s)
    assert isinstance(a, DeribitOAuth)
