import { BaseExchange } from "../../core/exchange";
import { createHttpClient } from "../../core/httpClient";
import { ExchangeCoinSnapshot } from "../../types";

type PerpetualMarket = {
  clobPairId: string;
  ticker: string;
  status: string;
  oraclePrice: string;
  priceChange24H: string;
  volume24H: string;
  trades24H: number;
  nextFundingRate: string;
  initialMarginFraction: string;
  maintenanceMarginFraction: string;
  openInterest: string;
  atomicResolution: number;
  quantumConversionExponent: number;
  tickSize: string;
  stepSize: string;
  stepBaseQuantums: number;
  subticksPerTick: number;
  marketType: string;
  openInterestLowerCap: string;
  openInterestUpperCap: string;
  baseOpenInterest: string;
  defaultFundingRate1H: string;
};

type PerpetualMarkets = {
  markets: {
    [key: string]: PerpetualMarket;
  };
};

export class DydxExchange extends BaseExchange {
  readonly name = "dydx";
  private http = createHttpClient("https://indexer.dydx.trade");

  getFees() {
    const takerFee = 0.005;
    const makerFee = -0.001;
    return { takerFee, makerFee };
  }

  async fetchAllCoins(): Promise<ExchangeCoinSnapshot[]> {
    const { data } = await this.http.get<PerpetualMarkets>(
      "/v4/perpetualMarkets"
    );

    const res: ExchangeCoinSnapshot[] = [];

    for (const key in data.markets) {
      const market = data.markets[key];

      if (!market.ticker.endsWith("-USD")) continue;

      const fr = Number(market.nextFundingRate);
      if (isNaN(fr)) continue;

      const ratePct8h = fr * 8 * 100;

      res.push({
        indexPrice: +market.oraclePrice,
        base: market.ticker.replace(/-USD$/, ""),
        fundingRatePct8h: ratePct8h,
        rateFraction: fr,
        timestamp: Date.now(),
        nextFundingTime: Date.now() + 8 * 60 * 60 * 1000,
      } as ExchangeCoinSnapshot);
    }

    return res;
  }

  fetchCoin(coin: string): Promise<ExchangeCoinSnapshot | null> {
    throw new Error("Method not implemented.");
  }
}
