// src/core/exchange.ts

import { ExchangeCoinSnapshot } from "../types";

export interface Exchange {
  readonly name: string;

  getFees(): { takerFee: number; makerFee: number };
  fetchAllCoins(): Promise<ExchangeCoinSnapshot[]>;
  fetchCoin(coin: string): Promise<ExchangeCoinSnapshot | null>;
}

export abstract class BaseExchange {
  abstract name: string;
  abstract fetchAllCoins(): Promise<ExchangeCoinSnapshot[]>;

  async getHighFundingCoins(
    numberOfCoins: number = 10
  ): Promise<ExchangeCoinSnapshot[]> {
    const coins = await this.fetchAllCoins();

    const sortedCoins = coins
      .filter((c) => c.fundingRatePct8h !== undefined)
      .sort((a, b) => b.fundingRatePct8h! - a.fundingRatePct8h!);

    return [
      ...sortedCoins.slice(0, numberOfCoins / 2),
      ...sortedCoins.slice(-numberOfCoins / 2),
    ];
  }
}
