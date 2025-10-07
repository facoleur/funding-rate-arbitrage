// src/main.ts

import { COINS_TO_FETCH } from "./constants";
import { AsterExchange } from "./exchanges/aster/asterExchange";
import { HyperliquidExchange } from "./exchanges/hyperliquid/hyperliquidExchange";
import { computeDiff } from "./services/fundingDiffService";

(async () => {
  console.log("Fetching Aster data...");
  const aster = new AsterExchange();
  const asterData = await aster.fetchFunding();

  // Sort by funding rate to get extremes
  const sortedAster = [...asterData].sort((a, b) => b.ratePct8h - a.ratePct8h);
  const top20 = sortedAster.slice(0, COINS_TO_FETCH / 2);
  const bottom20 = sortedAster.slice(-COINS_TO_FETCH / 2);

  // Merge and normalize base tickers (strip 'USDT' suffix, uppercase)
  const interestingCoins = Array.from(
    new Set(
      [...top20, ...bottom20]
        .map((a) => a.base.replace(/USD(T)?$/, "").toUpperCase())
        .filter(Boolean)
    )
  );

  console.log(interestingCoins.join(", "));

  console.log("\nFetching Hyperliquid data for selected tokens...");
  const hyper = new HyperliquidExchange();
  const hyperData = await hyper.fetchHistoricalFunding();

  const diffs = computeDiff(asterData, hyperData);

  console.log("\n🔍 Top Funding Rate Differentials (Aster vs Hyperliquid)\n");
  console.table(diffs.slice(0, 10), [
    "base",
    "asterRate",
    "hyperRate",
    "diff",
    "apr",
    "asterTimestamp",
    "hyperTimestamp",
    "interval",
  ]);
})();
