// src/services/fundingDiffService.ts
import { CoinMatrix, ExchangeCoinSnapshot } from "../types";

export function filterExistingCoins(
  aster: ExchangeCoinSnapshot[],
  hyper: ExchangeCoinSnapshot[]
): { aster: ExchangeCoinSnapshot; hyper: ExchangeCoinSnapshot }[] {
  // Create a lookup map for Hyper coins by uppercase base
  const hyperMap = new Map(hyper.map((h) => [h.base.toUpperCase(), h]));

  const matchedPairs: {
    aster: ExchangeCoinSnapshot;
    hyper: ExchangeCoinSnapshot;
  }[] = [];

  for (const a of aster) {
    const base = a.base.toUpperCase();
    const h = hyperMap.get(base);
    if (!h) continue;

    matchedPairs.push({ aster: a, hyper: h });
  }

  return matchedPairs;
}

// export function computeDiff(
//   aster: ExchangeCoinSnapshot[],
//   hyper: ExchangeCoinSnapshot[]
// ) {
//   // Get directly matched pairs from the updated filterExistingCoins
//   const pairs = filterExistingCoins(aster, hyper);
//   const diffs = [];

//   for (const { aster: a, hyper: h } of pairs) {
//     // Normalize case
//     const base = a.base.toUpperCase();

//     // Ensure both are numeric
//     const asterRatePct8h = +Number(a.fundingRatePct8h).toFixed(4);
//     const hyperRatePct8h = +Number(h.fundingRatePct8h).toFixed(4);
//     if (isNaN(asterRatePct8h) || isNaN(hyperRatePct8h)) {
//       console.warn(
//         `Skipping ${base} due to invalid rates:`,
//         asterRatePct8h,
//         hyperRatePct8h
//       );
//       continue;
//     }

//     // Extract timestamps
//     const asterTimestamp = a.timestamp;
//     const hyperTimestamp = h.timestamp;

//     const asterPrice = +Number(a.indexPrice).toFixed(4);
//     const hyperPrice = +Number(h.indexPrice).toFixed(4);

//     const priceDiff = asterPrice - hyperPrice;
//     const priceDiffPct =
//       hyperPrice !== 0 ? +((priceDiff / hyperPrice) * 100).toFixed(4) : null;

//     // Compute differences
//     const diff = asterRatePct8h - hyperRatePct8h;
//     const apr = Math.abs(+(diff * 3 * 365).toFixed(4));

//     const action: "LONG_ASTER" | "LONG_HYPER" =
//       diff < 0 ? "LONG_ASTER" : "LONG_HYPER";

//     diffs.push({
//       base,
//       asterRatePct8h,
//       hyperRatePct8h,
//       diff,
//       apr,
//       asterTimestamp,
//       hyperTimestamp,
//       asterPrice,
//       hyperPrice,
//       priceDiffPct,
//       action,
//       asterInterval: a.fundingInterval,
//     });
//   }

//   // Sort by absolute difference (largest first)
//   return diffs.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
// }

export function filterBestCoinEntries(matrix: CoinMatrix[]): CoinMatrix[] {
  const bestByCoin = new Map<string, CoinMatrix>();

  for (const entry of matrix) {
    const existing = bestByCoin.get(entry.coin);

    if (!existing || (entry.apr ?? 0) > (existing.apr ?? 0)) {
      bestByCoin.set(entry.coin, entry);
    }
  }

  return Array.from(bestByCoin.values());
}

export function computeMatrix(
  exchangesData: { exchange: string; marketData: ExchangeCoinSnapshot[] }[]
): CoinMatrix[] {
  const marketMap = new Map<string, Record<string, ExchangeCoinSnapshot>>();

  for (const { exchange, marketData } of exchangesData) {
    for (const coin of marketData) {
      const base = coin.base.toUpperCase();
      if (!marketMap.has(base)) marketMap.set(base, {});
      marketMap.get(base)![exchange] = coin;
    }
  }

  const results: CoinMatrix[] = [];

  for (const [base, snapshotsByExchange] of marketMap.entries()) {
    const exchanges = Object.keys(snapshotsByExchange);
    if (exchanges.length < 2) continue;

    for (let i = 0; i < exchanges.length; i++) {
      for (let j = i + 1; j < exchanges.length; j++) {
        const e1 = exchanges[i];
        const e2 = exchanges[j];
        const a = snapshotsByExchange[e1];
        const b = snapshotsByExchange[e2];

        const rate1 = +Number(a.fundingRatePct8h).toFixed(4);
        const rate2 = +Number(b.fundingRatePct8h).toFixed(4);
        if (isNaN(rate1) || isNaN(rate2)) continue;

        const price1 = +Number(a.indexPrice ?? a.longPrice).toFixed(4);
        const price2 = +Number(b.indexPrice ?? b.longPrice).toFixed(4);
        const priceDiff = price1 - price2;
        const priceDiffPct =
          price2 !== 0 ? +((priceDiff / price2) * 100).toFixed(4) : null;

        const diff = rate1 - rate2;
        const apr = Math.abs(+(diff * 3 * 365).toFixed(4));

        const whereLong = diff < 0 ? e1 : e2;
        const whereShort = diff < 0 ? e2 : e1;

        results.push({
          coin: base,
          exchanges: {
            [e1]: {
              frPct8h: rate1,
              price: price1,
              timestamp: a.timestamp,
            },
            [e2]: {
              frPct8h: rate2,
              price: price2,
              timestamp: b.timestamp,
            },
          },
          diff,
          apr,
          priceDiffPct,
          whereLong,
          whereShort,
        });
      }
    }
  }

  const sortedResults = results.sort((a, b) => a.coin.localeCompare(b.coin));

  const res = filterBestCoinEntries(sortedResults);

  return res;
}

// Assuming computeDiffs returns generic pairs like { base, e1, e2, diff, apr, ... }
export async function enrichDiffsWithAsterInterval(
  diffs: any[],
  aster: { fetchFundingInterval(base: string): Promise<number> }
) {
  const filteredDiffs = diffs; //.filter((d) => Math.abs(d.apr) >= 20);

  // Cache Aster intervals to avoid redundant calls
  const asterIntervalCache: Record<string, number> = {};

  await Promise.all(
    filteredDiffs.map(async (d) => {
      const { base, e1, e2 } = d;

      // Find if Aster is involved in this pair
      const asterSide = e1 === "Aster" ? "e1" : e2 === "Aster" ? "e2" : null;
      if (!asterSide) return; // Skip if Aster not in this comparison

      // Fetch or reuse interval
      if (!asterIntervalCache[base]) {
        asterIntervalCache[base] = await aster.fetchFundingInterval(base);
      }
      const interval = asterIntervalCache[base];

      // Adjust Aster’s rate
      const rateKey = `${asterSide === "e1" ? e1 : e2}RatePct8h`;
      d.asterInterval = interval;
      d[rateKey] = d[rateKey] * (8 / interval);

      // Recompute diff + APR correctly
      const rate1 = d[`${e1}RatePct8h`];
      const rate2 = d[`${e2}RatePct8h`];
      d.diff = rate1 - rate2;
      d.apr = Math.abs(d.diff * 3 * 365);
    })
  );

  return filteredDiffs;
}
