import type { OptionSpread } from "../services/compareOptions";
import { getExchange } from "./ExchangeRouter";

const MAX_LEG_SIZE_USD = 10_000;

export async function placeOrdersOnExchanges(data: OptionSpread) {
  const buyExchange = getExchange(data.buy_from);
  const sellExchange = getExchange(data.sell_to);

  const quantity = Math.min(data.maxSize, MAX_LEG_SIZE_USD);

  const buyParams = {
    instrument_name: data.buy_from_instrument,
    side: "buy" as const,
    price: data.buy_ask,
    underlying_price: data.buy_from_underlying_price,
    quantity,
    time_in_force: "fill_or_kill" as const,
  };

  const sellParams = {
    instrument_name: data.sell_to_instrument,
    side: "sell" as const,
    price: data.sell_bid,
    underlying_price: data.sell_to_underlying_price,
    quantity,
    time_in_force: "fill_or_kill" as const,
  };

  // Execute both legs simultaneously
  const [buyResult, sellResult] = await Promise.allSettled([
    buyExchange.placeOrder(buyParams),
    sellExchange.placeOrder(sellParams),
  ]);

  console.log("Buy result:", buyResult);
  console.log("Sell result:", sellResult);
}
