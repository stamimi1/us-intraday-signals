"""
Orchestrator.

  python engine.py            one live cycle: fetch bars, scan latest bar of
                              every (strategy x interval x symbol), open
                              virtual trades for fresh signals, resolve open
                              trades, write live/*.json, Telegram fresh ones.
  python engine.py --replay   walk recent history through the exact same
                              strategy code to seed the ledger with backfill
                              trades, so performance stats exist on day one.

Output files (live/):
  signals.json      current + recent signals per interval, for the dashboard
  performance.json  per strategy x interval forward-test stats
  ledger.json       full virtual trade state (persisted across runs via the
                    data-live branch)
"""
import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

import data_feed
import ledger as ledger_mod
import notify
from strategies import LABELS, REGISTRY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("engine")

# how many recent bars to walk per interval in --replay
REPLAY_BARS = {"5m": 350, "15m": 500, "1h": 700, "4h": 350}


def load_config() -> dict:
    with open(Path(__file__).parent / "config.yaml") as f:
        return yaml.safe_load(f)


def fetch_all(cfg: dict) -> dict:
    return {iv: data_feed.fetch_bars(cfg["universe"], iv) for iv in cfg["intervals"]}


def scan_interval(frames: dict, interval: str, cfg: dict) -> list:
    """Run every applicable strategy on the latest bar of every symbol."""
    signals = []
    for strat_name, params in cfg["strategies"].items():
        if interval not in params["intervals"]:
            continue
        module = REGISTRY[strat_name]
        for symbol, df in frames.items():
            try:
                sig = module.scan(symbol, df, interval, params, cfg)
            except Exception as exc:  # noqa: BLE001 - one bad symbol must not kill the cycle
                logger.warning("%s %s %s scan error: %s", strat_name, symbol, interval, exc)
                continue
            if sig:
                signals.append(sig)
    return signals


def write_outputs(cfg: dict, ledger: dict, cycle_signals: list, frames_by_iv: dict):
    live_dir = Path(cfg["output"]["live_dir"])
    live_dir.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)

    # keep a rolling recent-signals list (from ledger seen entries via open+closed)
    recent = []
    for t in (ledger["open"] + ledger["closed"][-120:]):
        recent.append({
            "strategy": t["strategy"], "symbol": t["symbol"], "interval": t["interval"],
            "direction": t["direction"], "entry": t["entry"], "stop": t["stop"],
            "target": t["target"], "bar_time": t["bar_time"],
            "status": "open" if "exit" not in t else t["outcome"],
            "r": t.get("r"), "source": t.get("source", "live"),
        })
    recent.sort(key=lambda s: s["bar_time"], reverse=True)

    by_interval = {iv: [] for iv in cfg["intervals"]}
    for s in cycle_signals:
        by_interval[s["interval"]].append(s)

    signals_payload = {
        "updated_at": now.isoformat(),
        "market_open": data_feed.market_open(cfg),
        "universe_size": len(cfg["universe"]),
        "fresh": cycle_signals,
        "by_interval": by_interval,
        "recent": recent[:80],
        "labels": LABELS,
    }
    (live_dir / "signals.json").write_text(json.dumps(signals_payload))

    stats = ledger_mod.compute_stats(ledger, cfg["ledger"]["rolling_window"])
    (live_dir / "performance.json").write_text(json.dumps({
        "updated_at": now.isoformat(),
        "table": stats,
        "open_positions": len(ledger["open"]),
        "closed_total": len(ledger["closed"]),
        "labels": LABELS,
    }))


def run_live(cfg: dict):
    live_dir = Path(cfg["output"]["live_dir"])
    ledger = ledger_mod.load(live_dir / "ledger.json")

    frames_by_iv = fetch_all(cfg)

    cycle_signals = []
    for iv in cfg["intervals"]:
        cycle_signals.extend(scan_interval(frames_by_iv.get(iv, {}), iv, cfg))

    fresh = []
    for sig in cycle_signals:
        if ledger_mod.open_trade(ledger, sig, "live", cfg["ledger"]["max_open_total"]):
            fresh.append(sig)

    ledger_mod.resolve_open_trades(ledger, frames_by_iv)
    ledger_mod.save(ledger, live_dir / "ledger.json", cfg["ledger"]["keep_closed"])
    write_outputs(cfg, ledger, cycle_signals, frames_by_iv)

    logger.info("cycle done: %d signals on latest bars (%d fresh), %d open, %d closed",
                len(cycle_signals), len(fresh), len(ledger["open"]), len(ledger["closed"]))
    notify.send_fresh_signals(fresh, LABELS, cfg)


def run_replay(cfg: dict):
    """Seed the ledger by walking recent history through the same scan code."""
    live_dir = Path(cfg["output"]["live_dir"])
    ledger = ledger_mod.load(live_dir / "ledger.json")
    frames_by_iv = fetch_all(cfg)

    opened = 0
    for iv in cfg["intervals"]:
        frames = frames_by_iv.get(iv, {})
        n_bars = REPLAY_BARS[iv]
        for strat_name, params in cfg["strategies"].items():
            if iv not in params["intervals"]:
                continue
            module = REGISTRY[strat_name]
            for symbol, df in frames.items():
                start = max(0, len(df) - n_bars)
                opened += ledger_mod.replay_walk(
                    ledger, module, strat_name, symbol, df, iv, params, cfg, start
                )

    ledger["closed"].sort(key=lambda t: t["exit_time"])
    ledger_mod.save(ledger, live_dir / "ledger.json", cfg["ledger"]["keep_closed"])
    write_outputs(cfg, ledger, [], frames_by_iv)
    logger.info("replay done: %d backfill trades opened, %d closed total",
                opened, len(ledger["closed"]))
    for row in ledger_mod.compute_stats(ledger, cfg["ledger"]["rolling_window"]):
        logger.info("  %-16s %-4s n=%-4d win%%=%-5.1f avgR=%-6.3f PF=%-5.2f %s",
                    row["strategy"], row["interval"], row["trades"], row["win_rate"],
                    row["avg_r"], row["profit_factor"], row["health"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", action="store_true", help="seed ledger from recent history")
    args = parser.parse_args()
    cfg = load_config()
    if args.replay:
        run_replay(cfg)
    else:
        run_live(cfg)


if __name__ == "__main__":
    main()
