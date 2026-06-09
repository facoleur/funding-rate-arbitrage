export interface OptionsExchange {
  name: string;

  placeOrder(params: {
    instrument_name: string;
    side: "buy" | "sell";
    price: number;
    quantity: number;
    order_type?: "limit" | "market";
    time_in_force?: "fill_or_kill";
  }): Promise<any>;
}
