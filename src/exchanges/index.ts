// src/exchanges/index.ts
// import { Exchange } from "../core/exchange";
// import { AsterExchange } from "./aster/asterExchange";
// import { HyperliquidExchange } from "./hyperliquid/hyperliquidExchange";

// export const EXCHANGES: Exchange[] = [
//   new AsterExchange(),
//   new HyperliquidExchange(),
// ];

export type Exchange = "derive" | "deribit";

export type OptionQuote = {
  exchange: Exchange;
  normalized_name: string;
  instrument_name: string;
  underlying_price?: number;
  strike: number;
  expiry: number;
  option_type: "C" | "P" | string;
  maker_fee_rate: number;
  taker_fee_rate: number;

  bid_price?: number;
  ask_price?: number;
  bid_qty?: number;
  ask_qty?: number;
};

export type OptionChainsByExchange = {
  [key in Exchange]: OptionQuote[];
};
