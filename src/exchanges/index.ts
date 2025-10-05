// src/exchanges/index.ts
import { Exchange } from "../core/exchange";
import { AsterExchange } from "./aster/asterExchange";
import { HyperliquidExchange } from "./hyperliquid/hyperliquidExchange";

export const EXCHANGES: Exchange[] = [
  new AsterExchange(),
  new HyperliquidExchange(),
];
