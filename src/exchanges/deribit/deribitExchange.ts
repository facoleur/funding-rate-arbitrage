import Bottleneck from "bottleneck";
import { Exchange, OptionQuote } from "..";
import { createHttpClient } from "../../core/httpClient";
import { SIZE_TRHRESHOLD } from "../derive/deriveExchange";

const http = createHttpClient("https://www.deribit.com/api/v2/");

export class DeribitExchange {
  readonly name = "deribit";

  // Get all non-expired option instruments for a given currency
  async getOptionInstruments(symbol: string) {
    const response = await http.post("", {
      jsonrpc: "2.0",
      id: 1,
      method: "public/get_instruments",
      params: {
        currency: symbol.toUpperCase(),
        kind: "option",
        expired: false,
      },
    });

    if (!response?.data?.result) {
      throw new Error("Failed to fetch option instruments");
    }

    return response.data.result;
  }

  // Filter the instruments for a given expiration date
  async getOptionChainForDate(
    symbol: string,
    targetDate: Date
  ): Promise<OptionQuote[]> {
    const instruments = await this.getOptionInstruments(symbol);

    // Deribit uses expiry timestamps (ms), so match the day
    const months = [
      "JAN",
      "FEB",
      "MAR",
      "APR",
      "MAY",
      "JUN",
      "JUL",
      "AUG",
      "SEP",
      "OCT",
      "NOV",
      "DEC",
    ];
    const dd = String(targetDate.getUTCDate()).padStart(2, "0");
    const mon = months[targetDate.getUTCMonth()];
    const yyyy = String(targetDate.getUTCFullYear()).slice(-2);
    const targetDateStr = `${dd}${mon}${yyyy}`;

    const filtered = instruments.filter((inst: any) =>
      inst.instrument_name.includes(targetDateStr)
    );

    const options = filtered.map((inst: any) => ({
      normalized_name: normalizeInstrumentName(inst.instrument_name),
      instrument_name: inst.instrument_name,
      option_type: inst.option_type === "call" ? "C" : "P",
      strike: inst.strike,
      expiry: inst.expiration_timestamp,
      maker_fee_rate: inst.maker_commission,
      taker_fee_rate: inst.taker_commission,
    }));

    // console.log(options);

    return options;
  }

  // Fetch the current ticker (price, bid/ask, etc.) for one option
  async getOptionTicker(instrumentName: string) {
    const response = await http.post("", {
      jsonrpc: "2.0",
      id: 1,
      method: "public/ticker",
      params: {
        instrument_name: instrumentName,
      },
    });

    if (!response?.data?.result) {
      throw new Error(`Failed to fetch ticker for ${instrumentName}`);
    }

    const ticker = response.data.result;

    const result = {
      bid_price: ticker.best_bid_price * ticker.underlying_price,
      ask_price: ticker.best_ask_price * ticker.underlying_price,
      bid_qty: ticker.best_bid_amount,
      ask_qty: ticker.best_ask_amount,
    };

    return result;
  }

  async getMockOptionChainPrices() {
    const chain = [];

    chain.push({
      exchange: this.name as Exchange,
      normalized_name: `XXX-101010-10-C`,
      instrument_name: `XXX-101010-10-C`,
      option_type: "P" as "P" | "C",
      strike: 50000,
      expiry: 1761000000000,
      maker_fee_rate: 0.001,
      taker_fee_rate: 0.002,
      bid_price: 1000,
      ask_price: 1010,
      bid_qty: 1,
      ask_qty: 1,
      underlying_price: 55000,
    });

    chain.push({
      exchange: this.name as Exchange,
      normalized_name: `XXX-101010-10-C`,
      instrument_name: `XXX-101010-10-C`,
      option_type: "P" as "P" | "C",
      strike: 50000,
      expiry: 1761000000000,
      maker_fee_rate: 0.001,
      taker_fee_rate: 0.002,
      bid_price: 980,
      ask_price: 990,
      bid_qty: 1,
      ask_qty: 1,
      underlying_price: 55000,
    });

    await Promise.resolve(chain);
    return chain;
  }

  // Combine option metadata with live prices
  async getOptionChainPrices(symbol: string, targetDate: Date): Promise<any[]> {
    const chain = await this.getOptionChainForDate(symbol, targetDate);

    const limiter = new Bottleneck({
      minTime: 20, // 50 requests per second
    });

    const pricedChain = await Promise.all(
      chain.map((opt) =>
        limiter.schedule(async () => {
          const ticker = await this.getOptionTicker(opt.instrument_name);

          if (+ticker.bid_price * +ticker.bid_qty < SIZE_TRHRESHOLD) {
            return null;
          }

          return {
            ...opt,
            exchange: this.name,
            normalized_name: normalizeInstrumentName(opt.instrument_name),
            bid_price: ticker.bid_price,
            ask_price: ticker.ask_price,
            bid_qty: ticker.bid_qty,
            ask_qty: ticker.ask_qty,
          };
        })
      )
    );

    return pricedChain.filter(Boolean);
  }
}

export function normalizeInstrumentName(instrument: string): string {
  const regex = /^([A-Z]+)-(\d{2})([A-Z]{3})(\d{2})-(\d+)-(C|P)$/;
  const match = instrument.match(regex);

  if (!match) {
    throw new Error(`Invalid instrument format: ${instrument}`);
  }

  const [_, coin, day, monthStr, year, strike, side] = match;

  const months: Record<string, string> = {
    JAN: "01",
    FEB: "02",
    MAR: "03",
    APR: "04",
    MAY: "05",
    JUN: "06",
    JUL: "07",
    AUG: "08",
    SEP: "09",
    OCT: "10",
    NOV: "11",
    DEC: "12",
  };

  const month = months[monthStr.toUpperCase()];
  if (!month) {
    throw new Error(`Invalid month: ${monthStr}`);
  }

  const fullYear = `20${year}`;

  const formatted = `${coin}-${fullYear}${month}${day}-${strike}-${side}`;
  return formatted;
}
