import { OptionQuote } from "../exchanges";

export type OptionMap = Map<string, OptionQuote[]>;

export type OptionSpread = {
  symbol: string;
  symbol_date: string;
  instrument: string;
  buy_from_instrument: string;
  sell_to_instrument: string;
  buy_from_underlying_price: number;
  sell_to_underlying_price: number;
  strike: number;
  bid_raw: number;
  ask_raw: number;
  bid_price: number;
  ask_price: number;
  type: string;
  expiration: string;
  buy_from: string;
  sell_to: string;
  buy_ask: number;
  sell_bid: number;
  spread: number;
  apr: number;
  maxSize: number;
  buyLink?: string;
  sellLink?: string;
};

function isValidQuote(q: OptionQuote): q is Required<OptionQuote> {
  return (
    q.bid_price !== undefined &&
    q.ask_price !== undefined &&
    q.bid_qty !== undefined &&
    q.ask_qty !== undefined &&
    q.bid_price > 0 &&
    q.ask_price > 0
  );
}

export function groupOptionsByInstrument(allQuotes: OptionQuote[]): OptionMap {
  const map: OptionMap = new Map();

  for (const quote of allQuotes) {
    const key = quote.normalized_name;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(quote);
  }

  return map;
}

export function compareOptions(optionGroups: OptionQuote[][]): OptionSpread[] {
  const now = Date.now();

  const results = optionGroups
    .map((quotes) => {
      if (quotes.length < 2) return null; // need at least 2 exchanges to compare

      // Ensure all are same instrument
      const nameSet = new Set(quotes.map((q) => q.normalized_name));
      if (nameSet.size > 1) {
        throw new Error(
          `Mismatched instruments in group: ${[...nameSet].join(", ")}`
        );
      }

      const instrument = quotes[0].normalized_name;
      const expiry = quotes[0].expiry;
      const daysToExp = (expiry - now) / (1000 * 60 * 60 * 24);

      // Filter only valid quotes (have prices and qty)
      const valid = quotes.filter(isValidQuote);

      if (valid.length < 2) return null;

      // Find lowest ask (best buy) and highest bid (best sell)
      const lowestAsk = valid.reduce((min, q) =>
        q.ask_price < min.ask_price ? q : min
      );
      const highestBid = valid.reduce((max, q) =>
        q.bid_price > max.bid_price ? q : max
      );

      if (lowestAsk.exchange === highestBid.exchange) return null; // no cross-exchange arb

      const priceDiffPct =
        ((highestBid.bid_price - lowestAsk.ask_price) / lowestAsk.ask_price) *
        100;
      const netDiffPct =
        priceDiffPct -
        (lowestAsk.taker_fee_rate + highestBid.taker_fee_rate) * 100;

      if (netDiffPct <= 0) return null; // no profit

      const apr = (netDiffPct / daysToExp) * 365;

      // Compute max executable notional size (based on liquidity)
      const maxSize = Math.min(
        lowestAsk.ask_qty * lowestAsk.ask_price,
        highestBid.bid_qty * highestBid.bid_price
      );

      const name = quotes[0].normalized_name;
      const firstDash = name.indexOf("-");
      const secondDash =
        firstDash === -1 ? -1 : name.indexOf("-", firstDash + 1);
      const symbol_date = secondDash === -1 ? name : name.slice(0, secondDash);

      return {
        symbol: name.slice(0, 3),
        symbol_date,
        instrument,
        buy_from_instrument: lowestAsk.instrument_name,
        sell_to_instrument: highestBid.instrument_name,
        buy_from_underlying_price: +lowestAsk.underlying_price,
        sell_to_underlying_price: +highestBid.underlying_price,
        strike: quotes[0].strike,
        bid_raw: highestBid.bid_price_raw,
        ask_raw: lowestAsk.ask_price_raw,
        type: quotes[0].option_type,
        expiration: `${daysToExp.toFixed(1)}d`,
        buy_from: lowestAsk.exchange,
        sell_to: highestBid.exchange,
        buy_ask: +lowestAsk.ask_price,
        sell_bid: +highestBid.bid_price,
        spread: +netDiffPct.toFixed(2),
        apr: +apr.toFixed(2),
        maxSize: +maxSize.toFixed(2),
      };
    })
    .filter(Boolean);

  return results as OptionSpread[];
}
