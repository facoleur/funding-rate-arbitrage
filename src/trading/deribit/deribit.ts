import axios, { AxiosInstance } from "axios";

interface DeribitAuthResponse {
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

export class DeribitAuth {
  private clientId: string;
  private clientSecret: string;
  private baseUrl: string;
  private accessToken?: string;
  private refreshToken?: string;
  private expiryTime = 0;

  constructor(clientId: string, clientSecret: string, testnet = false) {
    this.clientId = clientId;
    this.clientSecret = clientSecret;
    this.baseUrl = testnet
      ? "https://test.deribit.com/api/v2/"
      : "https://www.deribit.com/api/v2/";
  }

  private isTokenValid(): boolean {
    return !!this.accessToken && Date.now() < this.expiryTime - 30_000;
  }

  async authenticate(): Promise<void> {
    const res = await axios.get(`${this.baseUrl}public/auth`, {
      params: {
        grant_type: "client_credentials",
        client_id: this.clientId,
        client_secret: this.clientSecret,
      },
    });

    const data: DeribitAuthResponse = res.data.result;
    this.accessToken = data.access_token;
    this.refreshToken = data.refresh_token;
    this.expiryTime = Date.now() + data.expires_in * 1000;
  }

  async getAuthHeader(): Promise<{ Authorization: string }> {
    if (!this.isTokenValid()) {
      await this.authenticate();
    }
    return { Authorization: `Bearer ${this.accessToken}` };
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }
}

export class DeribitOptionsTrader {
  private http: AxiosInstance;
  private auth: DeribitAuth;
  private baseUrl: string;

  constructor(clientId: string, clientSecret: string, testnet = false) {
    this.auth = new DeribitAuth(clientId, clientSecret, testnet);
    this.baseUrl = this.auth.getBaseUrl();
    this.http = axios.create({ timeout: 10_000 });
  }

  private async request<T>(
    endpoint: string,
    params: Record<string, any> = {}
  ): Promise<T> {
    const headers = await this.auth.getAuthHeader();
    const res = await this.http.get(`${this.baseUrl}${endpoint}`, {
      headers,
      params,
    });
    return res.data.result as T;
  }

  // === MARKET DATA ===
  async getInstrument(instrumentName: string): Promise<any> {
    return this.request("public/get_instrument", {
      instrument_name: instrumentName,
    });
  }

  async getOrderBook(instrumentName: string): Promise<any> {
    return this.request("public/get_order_book", {
      instrument_name: instrumentName,
    });
  }

  // === TRADING ===
  async placeOrder(params: {
    instrument_name: string;
    side: "buy" | "sell";
    amount: number;
    order_type?: "limit" | "market";
    price?: number;
    time_in_force?: "fill_or_kill";
    label?: string;
  }): Promise<OrderResponse> {
    const {
      instrument_name,
      side,
      amount,
      order_type = "market",
      price,
      time_in_force = "fill_or_kill",
      label,
    } = params;

    const endpoint = side === "buy" ? "private/buy" : "private/sell";

    const payload: Record<string, any> = {
      instrument_name,
      amount,
      type: order_type,
      time_in_force,
      label: label ?? `arb-${Date.now()}`,
    };

    if (price && order_type === "limit") {
      payload.price = price;
    }

    const headers = await this.auth.getAuthHeader();

    const url = `${this.baseUrl}${endpoint}`;

    console.log("DERIBIT ORDER: ", url, payload);

    try {
      const res = await this.http.get(url, {
        headers,
        params: payload,
      });
      return res.data.result as OrderResponse;
    } catch (err: any) {
      console.error("❌ Network/Config Error:", err.message);

      // throw err;
    }
  }

  async cancelOrder(orderId: string): Promise<any> {
    return this.request("private/cancel", { order_id: orderId });
  }

  async getOpenOrders(instrumentName?: string): Promise<any[]> {
    const params = instrumentName ? { instrument_name: instrumentName } : {};
    return this.request("private/get_open_orders", params);
  }

  async getPositions(): Promise<any[]> {
    return this.request("private/get_positions");
  }
}
