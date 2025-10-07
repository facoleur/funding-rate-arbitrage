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

export interface FundingSnapshot {
  base: string; // e.g. "BTC"
  symbol: string;
  rateFraction?: number; // e.g. 0.0003
  avgRatePct8h?: number; // New field for average 8h percentage rate
  ratePct8h: number; // percentage for 8h window (0.03%)
  nextFundingTime?: number;
  timestamp: number;
  interval?: 1 | 2 | 4 | 8; // in hours
  maxLeverage?: number; // e.g. 20
}
