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
  const derive = new DeriveExchange();
  const deribit = new DeribitExchange();
  const aevo = new AevoExchange();

  const expiries = await derive.getAvailableDates("BTC");
  // const exp = await derive.getAvailableDates("BTC");
  // const expiries = exp.slice(0, 100);

  // const expiries = [new Date("2024-09-27")];

  // const tickers = ["BTC", "ETH"];
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

      // const a_chain: OptionQuote[] = await aevo.getOptionChainPrices(
      //   ticker,
      //   exp
      // );

      // const rows = compareOptionChains(l_chain, d_chain);
      // data.push(...rows);
      const grouped = groupOptionsByInstrument([
        ...l_chain,
        ...d_chain,
        // ...a_chain,
      ]);
      const results = compareOptions([...grouped.values()]);
      sendTelegramMessage(results);

      console.log(
        "ticker: ",
        ticker,
        "exp:",
        exp,
        "nbr of options:",
        results.length
      );

      if (results.length > 0) {
        console.table(results);
      }

      data.push(...results);
    }
  }

  // sendTelegramMessage(data);
  console.table(data);
})();
