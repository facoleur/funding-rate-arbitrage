// src/types/index.ts
export interface FundingSnapshot {
  symbol: string;       // Exchange symbol (BTCUSDT, BTC-PERP, etc.)
  base: string;         // Unified asset code (BTC, ETH...)
  ratePct8h: number;    // Funding rate % per 8 hours
  timestamp?: number;
}
