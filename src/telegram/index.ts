// ...existing code...
import axios from "axios";
import * as dotenv from "dotenv";
import { DeribitExchange } from "../exchanges/deribit/deribitExchange";
import { DeriveExchange } from "../exchanges/derive/deriveExchange";
import { OptionSpread } from "../services/compareOptions";

dotenv.config();

const BOT_TOKEN = process.env.BOT_TOKEN!;
const CHAT_ID = process.env.CHAT_ID!;

// helper: treat null/undefined/whitespace as empty
function isEmptyString(value: unknown): boolean {
  return value === null || value === undefined || String(value).trim() === "";
}

// Escape MarkdownV2 special characters
function escapeMdV2(text: string): string {
  return String(text).replace(/[_*\[\]()~`>#+\-=|{}.!]/g, (m) => `\\${m}`);
}

// Return a MarkdownV2-safe link or plain escaped name when url is empty
function mkLink(name: string, url: string): string {
  if (isEmptyString(url)) return escapeMdV2(name);
  return `[${escapeMdV2(name)}](${encodeURI(String(url))})`;
}

// ✅ Function to send Telegram messages
export async function sendTelegramMessage(data: OptionSpread[]) {
  for (const item of data) {
    const aprNum = parseFloat(item.apr);
    if (aprNum < 10) {
      console.log(
        `APR ${aprNum}% is below threshold, not sending Telegram message.`
      );
      return;
    }

    let buyLink = "";
    let sellLink = "";

    try {
      if (
        item.buy_from === "derive" &&
        typeof (DeriveExchange as any).getLinkForOption === "function"
      ) {
        buyLink = (DeriveExchange as any).getLinkForOption(item) ?? "";
      } else if (
        item.buy_from === "deribit" &&
        typeof (DeribitExchange as any).getLinkForOption === "function"
      ) {
        buyLink = (DeribitExchange as any).getLinkForOption(item) ?? "";
      }
    } catch (e) {
      // don't break the whole flow if link generation fails
      console.error("link generation error (buy):", e);
      buyLink = "";
    }

    try {
      if (
        item.sell_to === "derive" &&
        typeof (DeriveExchange as any).getLinkForOption === "function"
      ) {
        sellLink = (DeriveExchange as any).getLinkForOption(item) ?? "";
      } else if (
        item.sell_to === "deribit" &&
        typeof (DeribitExchange as any).getLinkForOption === "function"
      ) {
        sellLink = (DeribitExchange as any).getLinkForOption(item) ?? "";
      }
    } catch (e) {
      console.error("link generation error (sell):", e);
      sellLink = "";
    }

    item.buyLink = buyLink;
    item.sellLink = sellLink;
  }

  const message = data
    .map((item) => {
      const title = `*${escapeMdV2(String(item.symbol))} ${escapeMdV2(
        String(item.instrument)
      )}*`;
      const buyPart = `Buy from: ${mkLink(
        item.buy_from,
        item.buyLink ?? ""
      )} at ${escapeMdV2(String(item.buy_ask))}`;
      const sellPart = `Sell to: ${mkLink(
        item.sell_to,
        item.sellLink ?? ""
      )} at ${escapeMdV2(String(item.sell_bid))}`;
      const tail = `Spread: ${escapeMdV2(
        String(item.spread)
      )} APR: ${escapeMdV2(String(item.apr))}`;
      return `${title}\n${buyPart}\n${sellPart}\n${tail}\n`;
    })
    .join("\n");

  if (isEmptyString(message)) {
    return;
  }

  try {
    await axios.post(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
      chat_id: CHAT_ID,
      text: String(message),
      parse_mode: "MarkdownV2",
      disable_web_page_preview: true,
    });
    console.log("✅ Message sent:", message);
  } catch (error: any) {
    // show Telegram API error response body when available
    console.error(
      "❌ Failed to send Telegram message:",
      error?.response?.data ?? error?.message ?? error
    );
  }
}
// ...existing code...
