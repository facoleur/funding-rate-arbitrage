"""Structured (multi-leg) arbitrage detection — box spreads.

Standalone module: runs in the `workers` container alongside `services.screener`,
shares the `BookCache`, writes to its own `structured_opportunities` table. The
1:1 screener and the executor never touch it.
"""
