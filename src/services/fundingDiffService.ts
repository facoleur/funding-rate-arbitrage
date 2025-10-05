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
    const asterRate = Number(a.ratePct8h);
    const hyperRate = Number(h.ratePct8h);
    if (isNaN(asterRate) || isNaN(hyperRate)) continue;

    const diff = asterRate - hyperRate;
    diffs.push({
      base,
      asterRate,
      hyperRate,
      diff,
    });
  }

  // Sort by absolute difference
  return diffs.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
}
