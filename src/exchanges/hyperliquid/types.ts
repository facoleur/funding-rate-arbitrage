export type MarketInfo = {
  dayNtlVlm: string;
  funding: string;
  impactPxs: [string, string];
  markPx: string;
  midPx: string;
  openInterest: string;
  oraclePx: string;
  premium: string;
  prevDayPx: string;
};

export type UniverseAsset = {
  name: string;
  szDecimals: number;
  maxLeverage: number;
  onlyIsolated?: boolean;
};

export type DataStructure = [
  {
    universe: UniverseAsset[];
  },
  MarketInfo[]
];
