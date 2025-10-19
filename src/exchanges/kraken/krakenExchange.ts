// Retrieve ticker data for all instruments.
// Endpoint does not require authentication,
// but has utility functions for authentication.

import { BaseExchange } from "../../core/exchange";
import { createHttpClient } from "../../core/httpClient";
import { ExchangeCoinSnapshot } from "../../types";

export class krakenExchange extends BaseExchange {
  readonly name = "kraken";
  private http = createHttpClient("https://futures.kraken.com");

  async getFees(): Promise<{ takerFee: number; makerFee: number }> {
    const { data } = await this.http.get("/derivatives/api/v3/feeschedules");

    const takerFee = data.feeSchedules[1].tiers[0].takerFee;
    const makerFee = data.feeSchedules[1].tiers[0].makerFee;

    return { takerFee, makerFee };
  }

  async fetchAllCoins(): Promise<ExchangeCoinSnapshot[]> {
    const { data } = await this.http.get("/derivatives/api/v3/tickers");

    const res: ExchangeCoinSnapshot[] = [];

    data.tickers.forEach((d: any) => {
      if (!d.pair.endsWith(":USD")) return;

      if (d.pair.startsWith("XBT")) {
        return;
      }

      if (d.tag !== "perpetual" || !d.symbol.startsWith("PF_")) {
        return;
      }

      const frPct1h = (d.fundingRate / d.indexPrice) * 100;

      const apr = frPct1h * 24 * 365;

      res.push({
        base: d.pair.replace(/:USD$/, ""),
        longPrice: d.ask,
        shortPrice: d.bid,
        // fundingRatePct8h: d.fundingRate * 100 * 8,
        fundingRatePct8h: frPct1h * 8,
        timestamp: Date.now(),
        fundingInterval: 1,
      });
    });

    return res;
  }

  async getHighFundingCoins(
    numbersOfCoins: number = 10
  ): Promise<ExchangeCoinSnapshot[]> {
    const coins = await this.fetchAllCoins();

    const sortedCoins = coins
      .filter((coin) => coin.fundingRatePct8h !== undefined)
      .sort((a, b) => b.fundingRatePct8h! - a.fundingRatePct8h!);

    return [
      ...sortedCoins.slice(0, numbersOfCoins / 2),
      ...sortedCoins.slice(-numbersOfCoins / 2),
    ];
  }
}
