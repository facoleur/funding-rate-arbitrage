// // src/main.ts

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
      sendTelegramMessage(results);

      console.log("ticker: ", ticker, "opportunities: ", results.length);

      if (results.length > 0) {
        console.table(results);
      }

      data.push(...results);
    }
  }

  console.table(data);
}
