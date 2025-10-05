// src/core/exchange.ts
import { FundingSnapshot } from "../types";

export interface Exchange {
  readonly name: string;

  /** Returns normalized funding data: { symbol, ratePct8h } */
  fetchFunding(): Promise<FundingSnapshot[]>;

  /** Optionally returns a mapping from exchange-specific symbol -> base asset */
  mapSymbol?(symbol: string): string;
}
