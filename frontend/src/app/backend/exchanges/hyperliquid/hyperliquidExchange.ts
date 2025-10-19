import { BaseExchange } from "../../core/exchange";
import { createHttpClient } from "../../core/httpClient";
import { ExchangeCoinSnapshot } from "../../types";
import { DataStructure } from "./types";

const http = createHttpClient("https://api.hyperliquid.xyz");

async function parseFundingData(): Promise<ExchangeCoinSnapshot[]> {
  const resp = await http.post<DataStructure>("/info", {
    type: "metaAndAssetCtxs",
  });

  const [meta, marketData] = resp.data;
  const universe = meta.universe;

  return marketData
    .map((item, i) => ({
      ...item,
      name: universe[i].name,
      maxLeverage: universe[i].maxLeverage,
    }))
    .map((item) => {
      const fr = Number(item.funding);
      if (isNaN(fr)) return null;

      const ratePct8h = fr * 8 * 100;

      const now = Date.now();

      if (!item.midPx) return null;

      return {
        indexPrice: +Number(item.midPx).toFixed(4),
        shortPrice: +item.impactPxs[1],
        longPrice: +item.impactPxs[0],
        base: item.name,
        fundingRatePct8h: ratePct8h,
        rateFraction: fr,
        timestamp: now,
        nextFundingTime: now + 8 * 60 * 60 * 1000,
      } as ExchangeCoinSnapshot;
    })
    .filter(Boolean) as ExchangeCoinSnapshot[];
}

export class HyperliquidExchange extends BaseExchange {
  readonly name = "hyper";

  mapSymbol?(symbol: string): string {
    throw new Error("Method not implemented.");
  }

  getFees() {
    const takerFee = 0.0045;
    const makerFee = -0.0015;
    return { takerFee, makerFee };
  }

  async fetchCoin(coin: string): Promise<ExchangeCoinSnapshot | null> {
    const all = await this.fetchAllCoins();
    return all.find((c) => c.base === coin) || null;
  }

  async fetchAllCoins(): Promise<ExchangeCoinSnapshot[]> {
    try {
      return await parseFundingData();
    } catch (err) {
      console.warn(
        "Error fetching live Hyperliquid funding:",
        (err as Error).message
      );
      return [];
    }
  }
}
