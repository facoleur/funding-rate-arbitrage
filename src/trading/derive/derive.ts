interface DeriveAuthResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  scope: string;
  state: string;
  token_type: string;
}

interface OrderResponse {
  order: {
    order_id: string;
    instrument_name: string;
    direction: string;
    price: number;
    amount: number;
    filled_amount: number;
    state: string;
  };
}

export class DeriveAuth {}

export class DeriveOptionsTrader {
  private clientId: string;
  private clientSecret: string;
  private baseUrl: string;

  constructor(clientId: string, clientSecret: string, testnet = false) {
    this.clientId = clientId;
    this.clientSecret = clientSecret;
    this.baseUrl = testnet
      ? "https://testnet.derive.com"
      : "https://api.derive.com";
  }
  async placeOrder(params: {
    instrument_name: string;
    side: "buy" | "sell";
    amount: number;
    price: number;
    order_type?: "limit" | "market";
    time_in_force?: "fill_or_kill";
  }) {
    console.log("Derive orders: To implement");
  }
}
