// src/main.ts

import prisma from "@/lib/prisma";
import { AsterExchange } from "./exchanges/aster/asterExchange";
import { DydxExchange } from "./exchanges/dydx/dydxExchange";
import { HyperliquidExchange } from "./exchanges/hyperliquid/hyperliquidExchange";
import { krakenExchange } from "./exchanges/kraken/krakenExchange";
import { computeMatrix } from "./services/fundingDiffService";

export async function main() {
  const aster = new AsterExchange();
  const hyper = new HyperliquidExchange();
  const kraken = new krakenExchange();
  const dydx = new DydxExchange();

  const [asterData, hyperData, krakenData, dydxData] = await Promise.all([
    aster.fetchAllCoins(),
    hyper.fetchAllCoins(),
    kraken.fetchAllCoins(),
    dydx.fetchAllCoins(),
  ]);

  const exchangesData = [
    { exchange: aster.name, marketData: asterData },
    { exchange: hyper.name, marketData: hyperData },
    { exchange: kraken.name, marketData: krakenData },
    { exchange: dydx.name, marketData: dydxData },
  ];

  const matrix = computeMatrix(exchangesData);

  const cleanMatrix = matrix
    .filter((row) => row.coin) // ensure coin is defined
    .map((row) => {
      const e1 = Object.values(row.exchanges)[0];
      const e2 = Object.values(row.exchanges)[1];

      const safeNum = (v: unknown) =>
        typeof v === "number" && !isNaN(v) ? v : 0;

      return {
        coin: String(row.coin),
        e1fr: safeNum(e1.frPct8h),
        e2fr: safeNum(e2.frPct8h),
        e1price: safeNum(e1.price),
        e2price: safeNum(e2.price),
        diff: safeNum(row.diff),
        apr: safeNum(row.apr),
        priceDiffPct: safeNum(row.priceDiffPct),
        long: row.whereLong ?? "",
        short: row.whereShort ?? "",
      };
    });

  await prisma.history.createMany({
    data: cleanMatrix,
  });

  console.table(
    matrix
      .sort((a, b) => (a.apr ?? 0) - (b.apr ?? 0))
      .map(
        ({
          coin,
          exchanges,
          diff,
          apr,
          priceDiffPct,
          whereLong,
          whereShort,
        }) => ({
          coin,
          e1fr: Object.values(exchanges)[0].frPct8h,
          e2fr: Object.values(exchanges)[1].frPct8h,
          diff,
          apr,
          priceDiffPct,
          long: whereLong,
          short: whereShort,
        })
      )
  );
}
