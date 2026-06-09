// src/core/exchange.ts

export interface Exchange {
  readonly name: string;

  getFees(): { takerFee: number; makerFee: number };
}

export abstract class BaseExchange {}
