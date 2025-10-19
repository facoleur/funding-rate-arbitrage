import Bottleneck from "bottleneck";
import { Exchange, OptionQuote } from "..";
import { createHttpClient } from "../../core/httpClient";

export const SIZE_THRESHOLD = 100;

const http = createHttpClient("https://api.aevo.xyz/");

export class AevoExchange {
  readonly name = "aevo" as Exchange;

  private limiter = new Bottleneck({
    minTime: 1000, // e.g., ~50 req/sec
  });

  /** Returns a list of available option (and possibly other derivatives) instruments for a given underlying symbol */
  async getOptionInstruments(symbol: string): Promise<any[]> {
    const resp = await http.get("/markets", {
      params: { asset: symbol, instrument_type: "OPTION" },
    });

    return resp.data;
  }

  /** Get the option chain for a given underlying and target expiry date */
  async getOptionChainForDate(
    symbol: string,
    targetDate: Date
  ): Promise<OptionQuote[]> {
    const instruments = await this.getOptionInstruments(symbol);

    const start = new Date(targetDate);
    start.setUTCHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setUTCDate(end.getUTCDate() + 1);

    const filtered = instruments.filter((inst: any) => {
      // expiry can be string in nanoseconds, e.g. "1760947200000000000"
      const expiryNs = BigInt(inst.expiry);
      const expiryMs = Number(expiryNs / 1_000_000n); // convert ns → ms safely

      return expiryMs >= start.getTime() && expiryMs < end.getTime();
    });
    // Map to your internal OptionQuote format (partial)
    const options: OptionQuote[] = filtered.map((inst: any) => ({
      exchange: this.name,
      normalized_name: inst.instrument_name,
      instrument_name: inst.instrument_name,
      option_type: inst.option_type, // e.g. "C" or "P"
      strike: Number(inst.strike),
      expiry: new Date(inst.expiry).getTime(),
      maker_fee_rate: +inst.maker_fee_rate,
      taker_fee_rate: +inst.taker_fee_rate,
      // The price/qty fields will be filled in getOptionTicker
      bid_price: undefined,
      ask_price: undefined,
      bid_qty: undefined,
      ask_qty: undefined,
      underlying_price: undefined,
    }));

    return options;
  }

  /** Get ticker/quote data for a specific option instrument */
  async getOptionTicker(instrumentName: string): Promise<Partial<OptionQuote>> {
    const resp = await http.get(`/instrument/${instrumentName}`);

    if (!resp?.data) {
      throw new Error(`Failed to fetch ticker for ${instrumentName}`);
    }

    const ticker = resp.data;

    return {
      bid_price: +ticker.best_bid.price,
      ask_price: +ticker.best_ask.price,
      bid_qty: +ticker.best_bid.amount,
      ask_qty: +ticker.best_ask.amount,
      underlying_price: +ticker.index_price,
    };
  }

  /** Get full option chain with live prices for a specific date and underlying */
  async getOptionChainPrices(
    symbol: string,
    targetDate: Date
  ): Promise<OptionQuote[]> {
    const chain = await this.getOptionChainForDate(symbol, targetDate);

    const pricedChain = await Promise.all(
      chain.map((opt) =>
        this.limiter.schedule(async () => {
          const ticker = await this.getOptionTicker(opt.instrument_name);
          console.log("got ticker");

          if (
            (ticker.bid_price ?? 0) * (ticker.bid_qty ?? 0) <
            SIZE_THRESHOLD
          ) {
            return null;
          }

          return {
            ...opt,
            bid_price: ticker.bid_price!,
            ask_price: ticker.ask_price!,
            bid_qty: ticker.bid_qty!,
            ask_qty: ticker.ask_qty!,
            underlying_price: ticker.underlying_price!,
          };
        })
      )
    );

    // Filter out nulls (smaller size / no data)
    return pricedChain.filter((x): x is OptionQuote => x !== null);
  }
}
