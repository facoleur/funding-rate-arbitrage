import { Exchange } from "../../core/exchange";
import { createHttpClient } from "../../core/httpClient";
import { FundingSnapshot } from "../../types";

export class AsterExchange implements Exchange {
  fetchHistoricalFunding(): Promise<FundingSnapshot[]> {
    throw new Error("Method not implemented.");
  }

  mapSymbol?(symbol: string): string {
    throw new Error("Method not implemented.");
  }

  readonly name = "Aster";
  private http = createHttpClient("https://fapi.asterdex.com");

  // --- helpers --------------------------------------------------------------

  /** Round a timestamp to the nearest hour in UTC if within a small tolerance. */
  private normalizeToUtcHour(
    ts: number,
    toleranceMin = 5
  ): { hour: number; ok: boolean } {
    const d = new Date(ts);
    const m = d.getUTCMinutes();
    let hour = d.getUTCHours();

    // Snap minutes close to :00 (handle small server drifts)
    if (m >= 60 - toleranceMin) {
      hour = (hour + 1) % 24;
      return { hour, ok: true };
    } else if (m <= toleranceMin) {
      return { hour, ok: true };
    } else {
      return { hour, ok: false };
    }
  }

  /**
   * Estimate funding interval from nextFundingTime using the anchor:
   *  - 8h ticks at 00,08,16 UTC
   *  - 4h ticks at 04,12,20 UTC
   *  - 2h ticks at remaining even UTC hours
   *  - 1h ticks at odd UTC hours
   *
   * We choose the *largest* interval consistent with the observed hour.
   */
  private estimateIntervalFromNext(nextFundingTime: number): 1 | 2 | 4 | 8 {
    const HOURS_8H = new Set([0, 8, 16]);
    const HOURS_4H = new Set([4, 12, 20]);

    const { hour, ok } = this.normalizeToUtcHour(nextFundingTime);
    if (!ok) {
      // If the minute isn't near :00, fall back to 1h (most conservative)
      return 1;
    }

    if (HOURS_8H.has(hour)) return 8;
    if (HOURS_4H.has(hour)) return 4;

    // Even hours not covered by 8h/4h -> 2h; odd hours -> 1h
    return hour % 2 === 0 ? 2 : 1;
  }

  // --- main -----------------------------------------------------------------

  async fetchFunding(): Promise<FundingSnapshot[]> {
    const { data } = await this.http.get("/fapi/v1/premiumIndex");

    // Some APIs return nextFundingTime; if not, we can't classify reliably.
    // We'll handle absent values gracefully.
    const nexts = data
      .map((d: any) => Number(d.nextFundingTime))
      .filter((v: number) => Number.isFinite(v) && v > 0);

    const maxNextFundingTime = nexts.length ? Math.max(...nexts) : undefined;

    return data.map((d: any) => {
      const fundingRate = Number(d.lastFundingRate); // per-period rate (period unknown)
      const nextFundingTime = Number(d.nextFundingTime); // expected to be ms epoch (UTC)

      let interval: 1 | 2 | 4 | 8 = 8; // default optimistic
      if (Number.isFinite(nextFundingTime) && nextFundingTime > 0) {
        interval = this.estimateIntervalFromNext(nextFundingTime);
      } else if (maxNextFundingTime) {
        // Fallback: compare to the farthest nextFundingTime we saw.
        // Map deltas to the nearest of {0,2,4,6,8} and choose the implied interval.
        const deltaH = (maxNextFundingTime - Number(d.time)) / 3_600_000;
        if (deltaH < 1.5) interval = 8;
        else if (deltaH < 3) interval = 4; // rough fallback only
        else if (deltaH < 5) interval = 2;
        else interval = 1;
      } else {
        // Worst-case: no signal → choose conservative 1h to avoid over-normalizing.
        interval = 1;
      }

      // Normalize the funding to 8h-equivalent for apples-to-apples comparison.
      const ratePct8h = fundingRate * (8 / interval) * 100;

      return {
        symbol: d.symbol,
        base: d.symbol.replace(/USDT$/, ""),
        ratePct8h, // 8h-normalized %
        ratePct: fundingRate * 100, // raw per-period %
        timestamp: d.time,
        interval,
        nextFundingTime: Number.isFinite(nextFundingTime)
          ? nextFundingTime
          : undefined,
      } as FundingSnapshot;
    });
  }
}
