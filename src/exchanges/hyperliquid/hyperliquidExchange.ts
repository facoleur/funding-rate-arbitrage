// src/exchanges/hyperliquid/hyperliquidExchange.ts

import { Exchange } from "../../core/exchange";
import { createHttpClient } from "../../core/httpClient";
import { FundingSnapshot } from "../../types";

interface HyperFundingRecord {
  coin: string;
  fundingRate: string;
  premium: string;
  time: number;
}

// ✅ Define default coins outside the class
export const DEFAULT_HYPERLIQUID_COINS = [
  "BTC",
  "ETH",
  "SOL",
  "ARB",
  "LINK",
  "OP",
  "AVAX",
  "DOGE",
  "BNB",
  "TIA",
];

/**
 * Hyperliquid Exchange implementation using the REST info endpoint.
 */
export class HyperliquidExchange implements Exchange {
  readonly name = "Hyperliquid";
  private http = createHttpClient("https://api.hyperliquid.xyz");
  private coins: string[];

  constructor(coins: string[] = DEFAULT_HYPERLIQUID_COINS) {
    this.coins = coins;
  }

  /** Fetch latest funding rates for each coin via fundingHistory. */
  async fetchFunding(): Promise<FundingSnapshot[]> {
    const results: FundingSnapshot[] = [];

    // Fetch each coin’s funding history in parallel
    const promises = this.coins.map(async (coin) => {
      try {
        const body = {
          type: "fundingHistory",
          coin,
          startTime: Date.now() - 24 * 60 * 60 * 1000, // last 24h
        };

        const resp = await this.http.post<HyperFundingRecord[]>("/info", body);
        const arr = resp.data;
        if (!Array.isArray(arr) || arr.length === 0) return null;

        const latest = arr[arr.length - 1];
        const fr = Number(latest.fundingRate);
        if (isNaN(fr)) return null;

        // Convert hourly rate → 8h percentage
        const ratePct8h = fr * 8 * 100;

        return {
          symbol: `${coin}-PERP`,
          base: coin,
          ratePct8h,
          rateFraction: fr, // Add rateFraction from fundingRate
          timestamp: latest.time,
          nextFundingTime: latest.time + 8 * 60 * 60 * 1000, // Estimate next funding time (+8h)
        } as FundingSnapshot;
      } catch (err) {
        console.warn(
          `Error fetching Hyperliquid funding for ${coin}:`,
          (err as Error).message
        );
        return null;
      }
    });

    const settled = await Promise.all(promises);
    for (const s of settled) {
      if (s) results.push(s);
    }

    return results;
  }
}
