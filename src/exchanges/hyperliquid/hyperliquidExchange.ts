import { Exchange } from "../../core/exchange";
import { createHttpClient } from "../../core/httpClient";
import { FundingSnapshot } from "../../types";
import { DataStructure } from "./types";

const http = createHttpClient("https://api.hyperliquid.xyz");

async function parseFundingData(): Promise<FundingSnapshot[]> {
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
      if (item.name.startsWith("APT")) {
        console.log(ratePct8h, item.name);
      }
      const now = Date.now();

      return {
        symbol: `${item.name}-PERP`,
        base: item.name,
        ratePct8h,
        rateFraction: fr,
        timestamp: now,
        nextFundingTime: now + 8 * 60 * 60 * 1000,
      } as FundingSnapshot;
    })
    .filter(Boolean) as FundingSnapshot[];
}

export class HyperliquidExchange implements Exchange {
  readonly name = "Hyperliquid";

  mapSymbol?(symbol: string): string {
    throw new Error("Method not implemented.");
  }

  async fetchHistoricalFunding(): Promise<FundingSnapshot[]> {
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
