// src/services/fundingDiffService.ts
import { FundingSnapshot } from "../types";

export function computeDiff(
  aster: FundingSnapshot[],
  hyper: FundingSnapshot[]
) {
  const hMap = new Map(hyper.map((h) => [h.base.toUpperCase(), h]));
  const diffs = [];

  for (const a of aster) {
    const base = a.base.toUpperCase();
    const h = hMap.get(base);
    if (!h) continue; // skip if Hyperliquid doesn't list this asset

    // Ensure both are numeric
    const asterRate = +Number(a.ratePct8h).toFixed(4);
    const hyperRate = +Number(h.ratePct8h).toFixed(4);
    if (isNaN(asterRate) || isNaN(hyperRate)) continue;

    const asterTimestamp = a.timestamp;
    const hyperTimestamp = h.timestamp;

    const diff = asterRate - hyperRate;

    const apr = Math.abs(+(diff * 3 * 365).toFixed(4));

    diffs.push({
      base,
      asterRate,
      hyperRate,
      diff,
      apr,
      asterTimestamp,
      hyperTimestamp,
      interval: a.interval,
    });
  }

  // Sort by absolute difference
  return diffs.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
}
