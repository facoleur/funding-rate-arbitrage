import { DeribitOptionsTrader } from "./deribit/deribit";
import { OptionsExchange } from "./OptionExchange";

export class DeribitExchange implements OptionsExchange {
  name = "deribit";
  private trader: DeribitOptionsTrader;

  constructor() {
    this.trader = new DeribitOptionsTrader(
      process.env.DERIBIT_CLIENT_ID!,
      process.env.DERIBIT_CLIENT_SECRET!,
      true
    );
  }

  async placeOrder(params: {
    instrument_name: string;
    side: "buy" | "sell";
    price: number;
    underlying_price: number;
    quantity: number;
    order_type?: "limit" | "market";
    time_in_force?: "fill_or_kill";
  }) {
    console.log("tamner", params.price, params.underlying_price);

    return this.trader.placeOrder({
      instrument_name: params.instrument_name,
      side: params.side,
      amount: params.quantity,
      price: params.price / params.underlying_price,
      order_type: params.order_type ?? "limit",
      time_in_force: params.time_in_force ?? "fill_or_kill",
    });
  }
}
