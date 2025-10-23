import Bottleneck from "bottleneck";
import { Exchange, OptionQuote } from "..";
import { createHttpClient } from "../../core/httpClient";
import { OptionSpread } from "../../services/compareOptions";

export const SIZE_TRHRESHOLD = 100;

const http = createHttpClient("https://api.lyra.finance/");

export class DeriveExchange {
  readonly name = "derive";
  static readonly baseTradeUrl = "https://app.derive.xyz/trade/options?";

  static getLinkForOption(instrument: OptionSpread) {
    return `${this.baseTradeUrl}symbol=${instrument.instrument}`;
  }

  async getAvailableDates(symbol: string): Promise<Date[]> {
    const response = await http.post("public/get_instruments", {
      expired: false,
      instrument_type: "option",
      currency: symbol,
    });

    const res: Date[] = [];
    const dates: Date[] = response.data.result.forEach((option: any) => {
      const date = new Date(option.option_details.expiry * 1000);
      if (!res.find((d) => d.getTime() === date.getTime())) {
        res.push(date);
      }
    });

    return res;
  }

  async getOptionInstruments(symbol: string) {
    const response = await http.post("public/get_instruments", {
      currency: symbol,
      instrument_type: "option",
      expired: false,
    });

    if (!response?.data?.result) {
      throw new Error("Failed to fetch option instruments");
    }

    return response.data.result;
  }

  async getOptionChainForDate(
    symbol: string,
    targetDate: Date
  ): Promise<OptionQuote[]> {
    const instruments = await this.getOptionInstruments(symbol);
    const stringDate = targetDate.toISOString().split("T")[0].replace(/-/g, "");
    instruments.filter((inst: any) =>
      inst.instrument_name.includes(stringDate)
    );

    const filtered = instruments.filter((inst: any) =>
      inst.instrument_name.includes(stringDate)
    );

    const options = filtered.map((inst: any) => ({
      instrument_name: inst.instrument_name,
      option_type: inst.option_details.option_type,
      strike: Number(inst.option_details.strike),
      expiry: inst.option_details.expiry * 1000, // to ms
      maker_fee_rate: +inst.maker_fee_rate,
      taker_fee_rate: +inst.taker_fee_rate,
    }));

    return options;
  }

  async getOptionTicker(instrumentName: string) {
    const response = await http.post("public/get_ticker", {
      instrument_name: instrumentName,
    });

    if (!response?.data?.result) {
      throw new Error(`Failed to fetch ticker for ${instrumentName}`);
    }

    const ticker = response.data.result;

    const result = {
      bid_price: +ticker.best_bid_price,
      ask_price: +ticker.best_ask_price,
      bid_qty: +ticker.best_bid_amount,
      ask_qty: +ticker.best_ask_amount,
      underlying_price: +ticker.underlying_price,
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
      bid_price: 1000,
      ask_price: 1010,
      bid_qty: 1,
      ask_qty: 1,
      underlying_price: 55000,
    });

    await Promise.resolve(chain);
    return chain;
  }

  async getOptionChainPrices(symbol: string, targetDate: Date): Promise<any[]> {
    const chain = await this.getOptionChainForDate(symbol, targetDate);

    const limiter = new Bottleneck({
      minTime: 15, // 100 requests per second
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
            normalized_name: opt.instrument_name,
            bid_price: +ticker.bid_price,
            ask_price: +ticker.ask_price,
            bid_qty: +ticker.bid_qty,
            ask_qty: +ticker.ask_qty,
            underlying_price: +ticker.underlying_price,
          };
        })
      )
    );

    return pricedChain.filter(Boolean);
  }
}
