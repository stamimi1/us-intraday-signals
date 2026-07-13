# ⚡ US Intraday Signals

Automated intraday signal engine for liquid US stocks/ETFs. Five
well-documented strategies scanned on 5m / 15m / 1h / 4h bars, a virtual
forward-testing ledger that continuously measures whether each strategy is
still working, and a mobile dashboard updated at ~1-minute cadence during
market hours.

**Dashboard:** https://stamimi1.github.io/us-intraday-signals/

## The five strategies

| Strategy | Intervals | Edge & provenance |
|---|---|---|
| **Opening Range Breakout** | 5m, 15m | First close beyond the first-15-min range with volume confirmation. Crabel (1990); Zarattini & Aziz (2023) documented a profitable 5-min ORB on liquid ETFs 2016-2023. Anti-chase guard skips late entries. |
| **VWAP Reversion** | 5m, 15m | Fade ±2σ extensions from session VWAP on the *re-entry* bar; target VWAP. Institutional benchmark anchoring + the documented intraday reversal effect. |
| **EMA 9/21 Trend Cross** | 15m, 1h, 4h | Cross in the direction of the 200-EMA trend. Trend-following is the most robust systematic edge on record (Brock/Lakonishok/LeBaron 1992; Moskowitz/Ooi/Pedersen 2012). |
| **RSI-2 Pullback** | 1h, 4h | Connors' short-term oversold dip inside an uptrend (RSI2<10, price>MA200). Decades of published backtests on liquid US equities; ATR stop added. |
| **Squeeze Breakout** | 15m, 1h, 4h | Bollinger-inside-Keltner compression released in the direction of momentum (TTM-squeeze family; volatility clustering). |

Every signal fires **only on its trigger bar** and always carries entry, stop
and target — no late alerts, no incomplete trade plans.

## Automated forward testing ("is it still working?")

Each fresh signal opens a **virtual trade**; the engine resolves stops,
targets, time-stops and end-of-day exits bar-by-bar (stop assumed first when
a bar spans both). Results in R multiples per strategy × interval: win rate,
average R, profit factor, rolling last-20 expectancy, and a health verdict
(`working` / `flat` / `degraded` / `collecting`). A `--replay` backfill walks
recent history through the identical code so stats exist from day one.

## Architecture

- `engine.py` — one cycle: batched yfinance fetch (1 request per interval for
  the whole ~40-symbol universe), scan, ledger update, JSON out, Telegram.
- GitHub Actions runs every 30 min in market hours; each job loops internally
  at 1-min cadence for ~27 min → near-continuous updates for $0.
- Data JSONs are force-pushed to the single-commit `data-live` branch; the
  dashboard (GitHub Pages, `docs/`) fetches them raw with a cache-buster
  every 60 s.

## Honest limitations

- These are the best-*documented* strategies, not guaranteed edges. Published
  edges decay; that is exactly what the health tracker is for.
- Virtual fills assume entry at the trigger close, no slippage/commissions.
  Real fills are worse, especially on 5m.
- Yahoo data can lag ~1 min; GitHub's scheduler can leave gaps between loop
  jobs.
- Educational tool. Not financial advice. Trade at your own risk, size with
  the ATR stop, never risk more than ~1% per trade.
