import { DeriveOptionsTrader } from "./derive/derive";
import { OptionsExchange } from "./OptionExchange";

export class DeriveExchange implements OptionsExchange {
  name = "Derive";
  private trader: DeriveOptionsTrader;

  constructor() {
    this.trader = new DeriveOptionsTrader(
      process.env.Derive_CLIENT_ID!,
      process.env.Derive_CLIENT_SECRET!,
      true
    );
  }

  async placeOrder(params: {
    instrument_name: string;
    side: "buy" | "sell";
    price: number;
    quantity: number;
    order_type?: "limit" | "market";
    time_in_force?: "fill_or_kill";
  }) {
    return this.trader.placeOrder({
      instrument_name: params.instrument_name,
      side: params.side,
      amount: params.quantity,
      price: params.price,
      order_type: params.order_type ?? "limit",
      time_in_force: params.time_in_force ?? "fill_or_kill",
    });
  }
}
