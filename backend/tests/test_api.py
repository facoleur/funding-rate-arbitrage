from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from option_arb.api.schemas import (
    AlertResponse,
    ErrorResponse,
    ExchangeStateResponse,
    ExecutorStateResponse,
    ExecutorToggleResponse,
    FundingHistoryResponse,
    HealthResponse,
    OpportunityResponse,
    OpportunityStatsResponse,
    PerpHedgeStateResponse,
    PerpHedgeToggleResponse,
    PositionResponse,
    StatusResponse,
    TickerResponse,
    TradeDetailResponse,
    TradeResponse,
)
from option_arb.db.models import Mode, Opportunity, OpportunityStatus
from option_arb.db.session import get_session
from option_arb.main import app


def _assert_not_free_form_schema(
    schema: dict[str, Any],
    components: dict[str, Any],
    context: str,
    seen_refs: set[str] | None = None,
) -> None:
    assert schema, f"empty schema: {context}"
    seen_refs = seen_refs or set()

    if ref := schema.get("$ref"):
        assert ref.startswith("#/components/schemas/"), f"unsupported reference: {context}"
        if ref in seen_refs:
            return
        name = ref.rsplit("/", 1)[-1]
        assert name in components, f"missing schema {name}: {context}"
        _assert_not_free_form_schema(components[name], components, context, seen_refs | {ref})
        return

    assert schema.get("additionalProperties") is not True, f"free-form object: {context}"
    assert any(
        keyword in schema for keyword in ("type", "anyOf", "oneOf", "allOf", "enum", "const")
    ), f"unstructured schema: {context}"

    if schema.get("type") == "object":
        has_properties = bool(schema.get("properties"))
        has_typed_values = isinstance(schema.get("additionalProperties"), dict)
        assert has_properties or has_typed_values, f"untyped object: {context}"

    for name, property_schema in schema.get("properties", {}).items():
        _assert_not_free_form_schema(property_schema, components, f"{context}.{name}", seen_refs)
    for keyword in ("items", "additionalProperties"):
        nested = schema.get(keyword)
        if isinstance(nested, dict):
            _assert_not_free_form_schema(nested, components, f"{context}.{keyword}", seen_refs)
    for keyword in ("anyOf", "oneOf", "allOf"):
        for index, nested in enumerate(schema.get(keyword, [])):
            _assert_not_free_form_schema(
                nested,
                components,
                f"{context}.{keyword}[{index}]",
                seen_refs,
            )


def test_openapi_has_named_schemas_for_all_json_responses() -> None:
    expected_models: dict[tuple[str, str], tuple[type[BaseModel], bool]] = {
        ("/health", "get"): (HealthResponse, False),
        ("/api/status", "get"): (StatusResponse, False),
        ("/api/opportunities/stats", "get"): (OpportunityStatsResponse, True),
        ("/api/opportunities", "get"): (OpportunityResponse, True),
        ("/api/opportunities/{opp_id}", "get"): (OpportunityResponse, False),
        ("/api/trades", "get"): (TradeResponse, True),
        ("/api/trades/{trade_id}", "get"): (TradeDetailResponse, False),
        ("/api/positions", "get"): (PositionResponse, True),
        ("/api/exchanges", "get"): (ExchangeStateResponse, True),
        ("/api/executor/state", "get"): (ExecutorStateResponse, False),
        ("/api/executor/kill", "post"): (ExecutorToggleResponse, False),
        ("/api/executor/resume", "post"): (ExecutorToggleResponse, False),
        ("/api/perp-hedge/state", "get"): (PerpHedgeStateResponse, False),
        ("/api/perp-hedge/pause", "post"): (PerpHedgeToggleResponse, False),
        ("/api/perp-hedge/resume", "post"): (PerpHedgeToggleResponse, False),
        ("/api/alerts", "get"): (AlertResponse, True),
        ("/api/tickers", "get"): (TickerResponse, True),
        ("/api/funding", "get"): (FundingHistoryResponse, True),
    }
    openapi = app.openapi()
    components = openapi["components"]["schemas"]

    successful_json_operations: set[tuple[str, str]] = set()
    http_methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    for path, path_item in openapi["paths"].items():
        for method, operation in path_item.items():
            if method not in http_methods:
                continue
            for status_code, response in operation["responses"].items():
                if not str(status_code).startswith("2"):
                    continue
                content = response.get("content", {})
                if "application/json" not in content:
                    continue
                successful_json_operations.add((path, method))
                _assert_not_free_form_schema(
                    content["application/json"].get("schema", {}),
                    components,
                    f"{method.upper()} {path} {status_code}",
                )

    assert set(expected_models) <= successful_json_operations

    for (path, method), (model, is_list) in expected_models.items():
        schema = openapi["paths"][path][method]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        expected_ref = {"$ref": f"#/components/schemas/{model.__name__}"}
        if is_list:
            assert schema["type"] == "array"
            assert schema["items"] == expected_ref
        else:
            assert schema == expected_ref

    for name, schema in components.items():
        if name.endswith("Response"):
            assert schema.get("additionalProperties") is False, name
    assert components["IsoDatetime"] == {"type": "string", "format": "date-time"}
    assert components["Network"]["enum"] == ["mainnet", "testnet"]

    opportunity_parameters = {
        parameter["name"]: parameter["schema"]
        for parameter in openapi["paths"]["/api/opportunities"]["get"]["parameters"]
    }
    assert opportunity_parameters["sort_by"]["enum"] == [
        "detected_at",
        "apr_pct",
        "spread_pct",
        "net_profit_usd",
        "max_notional_usd",
        "fees_usd",
    ]
    assert opportunity_parameters["sort_dir"]["enum"] == ["asc", "desc"]

    for path in ("/api/opportunities/{opp_id}", "/api/trades/{trade_id}"):
        error_schema = openapi["paths"][path]["get"]["responses"]["404"]["content"][
            "application/json"
        ]["schema"]
        assert error_schema == {"$ref": f"#/components/schemas/{ErrorResponse.__name__}"}

    stream_content = openapi["paths"]["/api/stream"]["get"]["responses"]["200"]["content"]
    assert "application/json" not in stream_content
    assert stream_content["text/event-stream"]["schema"] == {"type": "string"}


async def _insert_opportunity(**kwargs) -> Opportunity:  # type: ignore[no-untyped-def]
    defaults = dict(
        mode=Mode.PAPER,
        network="mainnet",
        instrument="BTC-20260101-30000-C",
        symbol="BTC",
        expiry=datetime.now(UTC) + timedelta(days=30),
        strike=30000.0,
        option_type="C",
        buy_from="derive",
        sell_to="deribit",
        top_ask=101.0,
        top_bid=110.0,
        spread_pct=8.85,
        fee_pct=0.06,
        apr_pct=107.0,
        max_notional_usd=1010.0,
        capital_deployed_usd=101.0,
        net_profit_usd=89.37,
        status=OpportunityStatus.PENDING,
    )
    defaults.update(kwargs)
    opp = Opportunity(**defaults)
    async with get_session() as sess:
        sess.add(opp)
        await sess.commit()
        await sess.refresh(opp)
    return opp


@pytest.mark.asyncio
async def test_health(test_db: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "path",
    ["/api/opportunities/999999", "/api/trades/999999"],
)
@pytest.mark.asyncio
async def test_detail_not_found_returns_documented_error(test_db: str, path: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get(path)
    assert r.status_code == 404
    assert r.json() == {"detail": "not found"}


@pytest.mark.parametrize(
    "path",
    [
        "/api/opportunities?network=devnet",
        "/api/opportunities/stats?network=devnet",
        "/api/opportunities?sort_by=id",
        "/api/opportunities?sort_dir=sideways",
    ],
)
@pytest.mark.asyncio
async def test_opportunity_literal_query_validation(test_db: str, path: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get(path)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_opportunities_empty(test_db: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/opportunities")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_opportunity_serialization_includes_profit_fields(test_db: str) -> None:
    # spread_pct=10.0, fee_pct=0.10, net_profit_usd=100 → fees = 100*0.10/10 = 1.0
    detected_at = datetime(2026, 1, 2, 3, 4, 5, 123456)
    await _insert_opportunity(
        detected_at=detected_at,
        max_notional_usd=1000.0,
        spread_pct=10.0,
        fee_pct=0.10,
        net_profit_usd=100.0,
        capital_deployed_usd=1000.0,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/opportunities")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    opp = body[0]
    assert "fee_pct" in opp
    assert "net_profit_usd" in opp
    assert "fees_usd" in opp
    assert "gross_profit_usd" in opp
    assert opp["fee_pct"] == pytest.approx(0.10)
    assert opp["net_profit_usd"] == pytest.approx(100.0, abs=0.01)
    assert opp["fees_usd"] == pytest.approx(1.0, abs=0.01)  # 100 * 0.10 / 10
    assert opp["gross_profit_usd"] == pytest.approx(101.0, abs=0.01)
    assert "capital_deployed_usd" in opp
    assert opp["detected_at"] == detected_at.isoformat()


@pytest.mark.asyncio
async def test_opportunity_stats_groups_by_pair(test_db: str) -> None:
    await _insert_opportunity(
        buy_from="derive",
        sell_to="deribit",
        max_notional_usd=1000.0,
        spread_pct=10.0,
        fee_pct=0.06,
        net_profit_usd=100.0,
    )
    await _insert_opportunity(
        buy_from="derive",
        sell_to="deribit",
        max_notional_usd=500.0,
        spread_pct=5.0,
        fee_pct=0.06,
        net_profit_usd=25.0,
    )
    await _insert_opportunity(
        buy_from="derive",
        sell_to="deribit_linear",
        max_notional_usd=200.0,
        spread_pct=8.0,
        fee_pct=0.06,
        net_profit_usd=16.0,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/opportunities/stats?days=30")
    assert r.status_code == 200
    stats = {s["pair"]: s for s in r.json()}

    assert "derive → deribit" in stats
    assert "derive → deribit_linear" in stats
    # derive → deribit: net_profit_usd 100 + 25 = 125
    assert stats["derive → deribit"]["total_net_profit_usd"] == pytest.approx(125.0, abs=0.01)
    assert stats["derive → deribit"]["count"] == 2
    assert stats["derive → deribit"]["best_net_profit_usd"] == pytest.approx(100.0, abs=0.01)
    # fees: 100*0.06/10 + 25*0.06/5 = 0.6 + 0.3 = 0.90
    assert stats["derive → deribit"]["total_fees_usd"] == pytest.approx(0.90, abs=0.01)


@pytest.mark.asyncio
async def test_opportunity_stats_empty(test_db: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/opportunities/stats")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_executor_state_default(test_db: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/executor/state")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("RUNNING", "KILLED")
    assert "config" in body and "counters" in body


@pytest.mark.asyncio
async def test_executor_kill_and_resume(test_db: str, temp_config, tmp_path) -> None:
    kill_path = tmp_path / "KILL"
    temp_config.write_text(f"limits:\n  kill_switch_file: {kill_path}\n")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert not kill_path.exists()
        r = await ac.post("/api/executor/kill")
        assert r.status_code == 200
        assert kill_path.exists()
        r = await ac.post("/api/executor/resume")
        assert r.status_code == 200
        assert not kill_path.exists()
