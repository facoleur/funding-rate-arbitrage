// // src/main.ts

import { log } from "console";
import { OptionQuote } from "./exchanges";
import { AevoExchange } from "./exchanges/Aevo/aveoExchange";
import { DeribitExchange } from "./exchanges/deribit/deribitExchange";
import { DeriveExchange } from "./exchanges/derive/deriveExchange";
import {
  compareOptions,
  groupOptionsByInstrument,
  OptionSpread,
} from "./services/compareOptions";
import { sendTelegramMessage } from "./telegram";
import { placeOrdersOnExchanges } from "./trading/orders";

(async () => {
  try {
    await runTask();
  } catch (error) {
    console.error("Error in main task:", error);
  }
})();

export async function runTask() {
  const derive = new DeriveExchange();
  const deribit = new DeribitExchange();
  const aevo = new AevoExchange();

  const expiries = await derive.getAvailableDates("BTC");
  const tickers = ["ETH"];

  const data: OptionSpread[] = [];
  for (const ticker of tickers) {
    for (const exp of expiries) {
      const l_chain: OptionQuote[] = await derive.getOptionChainPrices(
        ticker,
        exp
      );
      const d_chain: OptionQuote[] = await deribit.getOptionChainPrices(
        ticker,
        exp
      );

      const grouped = groupOptionsByInstrument([...l_chain, ...d_chain]);
      const results = compareOptions([...grouped.values()]);

      let orderPassed = false;
      for (const result of results) {
        if (result.apr && result.apr < 10) continue;

        if (orderPassed) {
          console.log("order already passed");
          continue;
        }

        log("Placing order:", result);

        placeOrdersOnExchanges(result);
        orderPassed = true;
        sendTelegramMessage(result);
      }

      console.log("ticker: ", ticker, "opportunities: ", results.length);

      if (results.length > 0) {
        console.table(results, [
          "instrument",
          "buy_from",
          "sell_to",
          "expiration",
          "spread",
          "apr",
        ]);
      }

      data.push(...results);
    }
  }

  console.table(data);
}

export async function test() {
  const mockSpread: OptionSpread = {
    symbol: "BTC",
    symbol_date: "BTC-31OCT25",
    instrument: "BTC-31OCT25-100000-C",
    buy_from_instrument: "BTC-31OCT25-100000-C",
    sell_to_instrument: "BTC-20251031-100000-C",
    buy_from_underlying_price: 1587,
    sell_to_underlying_price: 27100,
    strike: 30000,
    type: "call",
    expiration: "5.0d",
    buy_from: "derive",
    sell_to: "deribit",
    buy_ask: 1500,
    sell_bid: 2000,
    spread: 500,
    apr: 15,
    maxSize: 5000,
    buyLink: "",
    sellLink: "",
  };
}
