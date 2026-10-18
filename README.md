# Paper BTC/ETH Signal Desk v0.1

> **Personal record only. Not financial advice.**
> A "talk-only, never-trade" bot for BTC/ETH: it publishes a daily signal, records it,
> and reviews the win rate weekly. No orders are ever placed.

## Why this exists

The goal is an honest, verifiable public record of a simple rules-based signal system —
the kind of thing you can check against history instead of taking someone's word for it.
Every signal, the rule that produced it, and the weekly win-rate review are public.

## How it works — four roles

| Role | Watches | Signal rule (bullish / bearish / neutral) | Data source |
|---|---|---|---|
| Trend sentry | Daily trend direction | 4 votes: close > SMA20, close > SMA50, SMA20 > SMA50, MACD histogram > 0. ≥3 votes bullish, ≤1 bearish, else **neutral** | binance.vision daily klines (public) |
| Volatility officer | Volatility + grid-friendliness | ATR14 / price: >4% high, <2% low; 7-day avg range as context; ATR >2.5% = grid-friendly | Derived from the same klines |
| Funding-rate lookout | Perps long/short crowding | Binance App "next funding rate" pasted manually: ≥0.01% bearish (crowded longs), ≤−0.01% bullish; marked "pending" when missing | Manual paste (Binance fapi is geo-blocked from this server) |
| Sentiment scan | Emotion extremes | Fear & Greed index: ≤24 extreme-fear → bullish, 25–44 fear → bullish, 45–55 **neutral**, 56–74 greed → bearish, ≥75 extreme-greed → bearish | alternative.me/fng (public) |

**Composite signal**: trend 2 votes + funding 1 vote + sentiment 1 vote (volatility carries no
direction vote). Bullish = +1, bearish = −1. Total ≥ +2 → **bullish**, ≤ −2 → **bearish**,
else **hold**.

**Red lines**
- Record only, never trade. Signals ≠ investment advice.
- Signals are computed from the **previous daily close** — no lookahead. Intraday price is annotated as intraday only.

## Files

- `paper_signals.py` — stdlib-only script. `python3 paper_signals.py [funding_rate_pct]` writes one
  line to `signals.jsonl`; `python3 paper_signals.py --review` prints the win-rate review.
  Running twice on the same day keeps only the latest entry.
- `signals.jsonl` — the public signal log (one JSON object per day: date, per-role signals,
  composite, and the numbers behind them).
- `fetch_funding.py` — OKX public funding-rate history collector (research aid; the funding role
  itself uses Binance App numbers pasted manually).
- `funding_state.json` — local cache written by `fetch_funding.py`.

## Weekly review (win-rate ledger)

Once a week: for every bullish/bearish signal, check the close 7 days later. Hold/neutral
signals don't count. Output: a small table — role, signal count, win rate.
If a role stays below 50% for 4 consecutive weeks, its rule gets re-examined.

## Data sources (verified reachable, no API key needed)

- `data-api.binance.vision` — BTC/ETH daily klines ✅
- `api.alternative.me/fng/` — Fear & Greed index ✅
- `www.okx.com/api/v5/public/funding-rate-history` — funding-rate history ✅
- ❌ `fapi.binance.com` / `api.bybit.com` — geo-blocked from this server; funding numbers come
  from the Binance App, pasted manually.

## License

MIT
