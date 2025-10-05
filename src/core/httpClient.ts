// src/core/httpClient.ts
import axios, { AxiosInstance } from "axios";

export function createHttpClient(baseURL: string): AxiosInstance {
  return axios.create({
    baseURL,
    timeout: 15_000,
    headers: { "User-Agent": "FundingDiffBot/1.0" },
  });
}
