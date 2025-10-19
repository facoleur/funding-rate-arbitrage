// // src/main.ts

import { AevoExchange } from "./exchanges/Aevo/aveoExchange";
import { DeribitExchange } from "./exchanges/deribit/deribitExchange";
import { DeriveExchange } from "./exchanges/derive/deriveExchange";

// import { AsterExchange } from "./exchanges/aster/asterExchange";
// import { DydxExchange } from "./exchanges/dydx/dydxExchange";
// import { HyperliquidExchange } from "./exchanges/hyperliquid/hyperliquidExchange";
// import { krakenExchange } from "./exchanges/kraken/krakenExchange";
// import { computeMatrix } from "./services/fundingDiffService";
// import { ExchangeCoinSnapshot } from "./types";

// export async function main() {
//   const args = process.argv.slice(2);
//   const coinArg = args.find((arg) => arg.startsWith("coin="));
//   const coin = coinArg ? coinArg.split("=")[1].toUpperCase() : null;

//   const aster = new AsterExchange();
//   const hyper = new HyperliquidExchange();
//   const kraken = new krakenExchange();
//   const dydx = new DydxExchange();

//   if (coin) {
//     const [asterFunding, hyperFunding] = await Promise.all([
//       aster.fetchCoin(coin),
//       hyper.fetchCoin(coin),
//     ]);

//     // const diff = computeDiff([asterFunding!], [hyperFunding!]);

//     // console.table(diff, [
//     //   "base",
//     //   "asterRatePct8h",
//     //   "hyperRatePct8h",
//     //   "diff",
//     //   "apr",
//     //   "asterPrice",
//     //   "hyperPrice",
//     //   "priceDiffPct",
//     //   "action",
//     //   "asterInterval",
//     // ]);

//     return;
//   }

//   const [asterData, hyperData, krakenData, dydxData] = await Promise.all([
//     aster.fetchAllCoins(),
//     hyper.fetchAllCoins(),
//     kraken.fetchAllCoins(),
//     dydx.fetchAllCoins(),
//   ]);

//   const exchangesData = [
//     { exchange: aster.name, marketData: asterData },
//     { exchange: hyper.name, marketData: hyperData },
//     { exchange: kraken.name, marketData: krakenData },
//     { exchange: dydx.name, marketData: dydxData },
//   ];

//   const matrix = computeMatrix(exchangesData);

//   console.table(
//     matrix
//       .sort((a, b) => a.apr - b.apr)
//       .map(
//         ({
//           coin,
//           exchanges,
//           diff,
//           apr,
//           priceDiffPct,
//           whereLong,
//           whereShort,
//         }) => ({
//           coin,
//           e1fr: Object.values(exchanges)[0].frPct8h,
//           e2fr: Object.values(exchanges)[1].frPct8h,
//           diff,
//           apr,
//           priceDiffPct,
//           long: whereLong,
//           short: whereShort,
//         })
//       )
//   );

//   // console.table(updatedDiffs.slice(0, 5));

//   // console.table(filteredDiffs, [
//   //   "base",
//   //   "asterRatePct8h",
//   //   "hyperRatePct8h",
//   //   "diff",
//   //   "apr",
//   //   "asterPrice",
//   //   "hyperPrice",
//   //   "priceDiffPct",
//   //   "action",
//   //   "asterInterval",
//   // ]);
// }

// main();

// function getAllPairsMappedToExchanges(
//   exchangesData: { exchange: string; marketData: ExchangeCoinSnapshot[] }[]
// ) {
//   const exchanges = exchangesData.map((ed) => ed.exchange);
//   const coins: { coin: string; exchanges: string[] }[] = [];

//   for (const { exchange, marketData } of exchangesData) {
//     for (const coinSnapshot of marketData) {
//       const coinEntry = coins.find((c) => c.coin === coinSnapshot.base);
//       if (coinEntry) {
//         coinEntry.exchanges.push(exchange);
//       } else {
//         coins.push({ coin: coinSnapshot.base, exchanges: [exchange] });
//       }
//     }
//   }

//   const filteredCoins = coins.filter((c) => c.exchanges.length > 1);

//   return filteredCoins;
// }

(async () => {
  const derive = new DeriveExchange();
  const deribit = new DeribitExchange();
  const aevo = new AevoExchange();

  const expiriesString = [
    "2025-11-28",
    "2025-10-31",
    "2025-10-24",
    "2025-10-22",
    "2025-11-07",
    "2025-12-26",
  ];
  const expiries = expiriesString.map((d) => new Date(d));

  const tickers = ["BTC", "ETH"];

  const test = await aevo.getOptionChainPrices("BTC", new Date("2025-10-24"));
  console.log(test);

  // const data = [];

  // for (const ticker of tickers) {
  //   for (const exp of expiries) {
  //     const l_chain: OptionQuote[] = await derive.getOptionChainPrices(
  //       ticker,
  //       exp
  //     );
  //     const d_chain: OptionQuote[] = await deribit.getOptionChainPrices(
  //       ticker,
  //       exp
  //     );

  //     // const rows = compareOptionChains(l_chain, d_chain);
  //     // data.push(...rows);
  //     const grouped = groupOptionsByInstrument([...l_chain, ...d_chain]);
  //     const results = compareOptions([...grouped.values()]);

  //     console.log(
  //       "ticker: ",
  //       ticker,
  //       "exp:",
  //       exp,
  //       "nbr of options:",
  //       results.length
  //     );

  //     data.push(...results);
  //   }
  // }

  // console.table(data);
})();
