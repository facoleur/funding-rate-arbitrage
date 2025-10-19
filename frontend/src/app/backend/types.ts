export interface PremiumIndexItem {
  symbol: string;
  markPrice: string;
  indexPrice: string;
  estimatedSettlePrice?: string;
  lastFundingRate: string; // fraction (e.g. "0.0003" => 0.03%)
  nextFundingTime: number; // ms
  interestRate?: string;
  time: number; // ms
}

export interface ExchangeCoinSnapshot {
  base: string; // e.g. "BTC"
  shortPrice?: number;
  longPrice?: number;
  indexPrice?: number;
  rateFraction?: number; // e.g. 0.0003
  fundingRatePct8h?: number; // percentage for 8h window (0.03%)
  avgRatePct8h?: number; // New field for average 8h percentage rate
  nextFundingTime?: number;
  timestamp: number;
  fundingInterval?: 1 | 2 | 4 | 8; // in hours
  maxLeverage?: number; // e.g. 20
}

export type CoinMatrix = {
  coin: string;
  exchanges: {
    [exchange: string]: {
      frPct8h: number;
      price: number;
      timestamp: number;
    };
  };
  diff?: number;
  apr?: number;
  priceDiffPct: number | null;
  whereLong: string;
  whereShort: string;
};
