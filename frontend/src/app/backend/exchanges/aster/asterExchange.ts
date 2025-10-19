import { BaseExchange } from "../../core/exchange";
import { createHttpClient } from "../../core/httpClient";
import { ExchangeCoinSnapshot } from "../../types";

export class AsterExchange extends BaseExchange {
  readonly name = "aster";
  private http = createHttpClient("https://fapi.asterdex.com");

  async fetchAllFundingInterval(): Promise<
    { symbol: string; fundingInterval: 1 | 2 | 4 | 8 }[]
  > {
    const { data } = await this.http.get(
      `https://www.asterdex.com/bapi/futures/v1/public/future/common/real-time-funding-rate`
    );

    const res = [];

    for (const item of data.data) {
      res.push({
        symbol: item.symbol,
        fundingInterval: item.fundingIntervalHours as 1 | 2 | 4 | 8,
      });
    }
    return res;
  }

  async fetchFundingInterval(coin: string) {
    const symbol = coin + "USDT";
    const { data } = await this.http.get(
      `https://www.asterdex.com/bapi/futures/v1/public/future/common/real-time-funding-rate?symbol=${symbol}`
    );

    return data.data[0].fundingIntervalHours as 1 | 2 | 4 | 8;
  }

  async fetchCoin(coin: string): Promise<ExchangeCoinSnapshot | null> {
    const { data } = await this.http.get(
      `/fapi/v1/premiumIndex?symbol=${coin + "USDT"}`
    );

    const interval = await this.fetchFundingInterval(coin);
    data.interval = interval;
    data.ratePct8h = Number(data.lastFundingRate) * 100 * (8 / interval);

    return {
      indexPrice: +data.indexPrice,
      base: data.symbol.replace(/USDT$/, ""),
      fundingRatePct8h: data.ratePct8h,
      timestamp: data.time,
      nextFundingTime: Number.isFinite(data.nextFundingTime)
        ? data.nextFundingTime
        : undefined,
      fundingInterval: interval,
    } as ExchangeCoinSnapshot;
  }

  async fetchAllCoins(): Promise<ExchangeCoinSnapshot[]> {
    const { data } = await this.http.get("/fapi/v1/premiumIndex");
    const intervals = await this.fetchAllFundingInterval();

    const intervalMap = new Map<string, 1 | 2 | 4 | 8>();
    for (const { symbol, fundingInterval } of intervals) {
      intervalMap.set(symbol, fundingInterval);
    }
    data.forEach((d: any) => {
      d.interval = intervalMap.get(d.symbol) ?? 8;
    });

    // Some APIs return nextFundingTime; if not, we can't classify reliably.
    // We'll handle absent values gracefully.
    const nexts = data
      .map((d: any) => Number(d.nextFundingTime))
      .filter((v: number) => Number.isFinite(v) && v > 0);

    return data.map((d: any) => {
      const fundingRate = Number(d.lastFundingRate); // per-period rate (period unknown)
      const nextFundingTime = Number(d.nextFundingTime); // expected to be ms epoch (UTC)

      const ratePct8h = fundingRate * 100 * (8 / d.interval);

      return {
        indexPrice: d.indexPrice,
        symbol: d.symbol,
        base: d.symbol.replace(/USDT$/, ""),
        fundingRatePct8h: ratePct8h,
        ratePct: fundingRate * 100,
        timestamp: d.time,
        nextFundingTime: Number.isFinite(nextFundingTime)
          ? nextFundingTime
          : undefined,
      } as ExchangeCoinSnapshot;
    });
  }
}
