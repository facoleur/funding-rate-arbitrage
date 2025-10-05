// src/exchanges/aster/asterExchange.ts
import { Exchange } from "../../core/exchange";
import { createHttpClient } from "../../core/httpClient";
import { FundingSnapshot } from "../../types";

export class AsterExchange implements Exchange {
  readonly name = "Aster";
  private http = createHttpClient("https://fapi.asterdex.com");

  async fetchFunding(): Promise<FundingSnapshot[]> {
    const { data } = await this.http.get("/fapi/v1/premiumIndex");
    return data.map((d: any) => ({
      symbol: d.symbol,
      base: d.symbol.replace(/USDT$/, ""),
      ratePct8h: Number(d.lastFundingRate) * 100,
      timestamp: d.time,
    }));
  }
}
