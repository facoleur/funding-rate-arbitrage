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
  rateFraction: number; // e.g. 0.0003
  ratePct8h: number; // percentage for 8h window (0.03%)
  nextFundingTime: number;
}
