"""
Virtual paper-trade ledger: the automated forward-testing record.

Every fresh signal opens a virtual trade at its entry price. Each engine cycle
walks the bars printed since entry and resolves stop / target / time-stop /
end-of-day exits (if a bar spans both stop and target, the stop is assumed
first — conservative). Results are scored in R multiples (profit measured in
units of initial risk), which makes strategies directly comparable regardless
of price level or position size.

Health verdicts answer "is this strategy still working?" from the rolling
last-N closed trades.
"""
import json
import logging
import uuid
from datetime import datetime, time as dtime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

EOD_CUTOFF = dtime(15, 45)  # intraday trades flat at/after this bar


def load(path: str) -> dict:
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Ledger at %s unreadable; starting fresh", path)
    return {"open": [], "closed": [], "seen": {}}


def save(ledger: dict, path: str, keep_closed: int):
    ledger["closed"] = ledger["closed"][-keep_closed:]
    # trim seen keys older than ~10 days to bound file size
    if len(ledger["seen"]) > 20000:
        ledger["seen"] = dict(list(ledger["seen"].items())[-10000:])
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger))


def signal_key(sig: dict) -> str:
    return f"{sig['strategy']}|{sig['symbol']}|{sig['interval']}|{sig['bar_time']}"


def open_trade(ledger: dict, sig: dict, source: str, max_open: int) -> bool:
    """Open a virtual trade for a fresh signal. Returns True if opened."""
    key = signal_key(sig)
    if key in ledger["seen"]:
        return False
    ledger["seen"][key] = 1
    # one open position per strategy/symbol/interval
    for t in ledger["open"]:
        if (t["strategy"], t["symbol"], t["interval"]) == (sig["strategy"], sig["symbol"], sig["interval"]):
            return False
    if len(ledger["open"]) >= max_open:
        logger.warning("Ledger at max open positions; skipping %s", key)
        return False
    ledger["open"].append({
        "id": uuid.uuid4().hex[:10],
        "source": source,               # "live" | "backfill"
        **{k: sig[k] for k in ("strategy", "symbol", "interval", "direction",
                               "entry", "stop", "target", "risk", "bar_time",
                               "time_stop_bars", "eod_exit")},
    })
    return True


def _resolve_one(trade: dict, df: pd.DataFrame):
    """Walk bars after entry; return (exit_price, exit_time, outcome) or None."""
    entry_time = pd.Timestamp(trade["bar_time"])
    after = df[df.index > entry_time]
    if after.empty:
        return None
    long = trade["direction"] == "long"
    stop, target = trade["stop"], trade["target"]

    for n, (ts, bar) in enumerate(after.iterrows(), start=1):
        hit_stop = bar["low"] <= stop if long else bar["high"] >= stop
        hit_target = bar["high"] >= target if long else bar["low"] <= target
        if hit_stop:                       # stop first when both hit same bar
            return stop, ts, "stop"
        if hit_target:
            return target, ts, "target"
        if trade["eod_exit"] and (ts.time() >= EOD_CUTOFF or ts.date() > entry_time.date()):
            return bar["close"], ts, "eod"
        if trade["time_stop_bars"] and n >= trade["time_stop_bars"]:
            return bar["close"], ts, "time"
    return None


def close_record(trade: dict, exit_price, exit_time, outcome: str) -> dict:
    sign = 1 if trade["direction"] == "long" else -1
    r = sign * (exit_price - trade["entry"]) / trade["risk"] if trade["risk"] else 0.0
    return {
        **trade,
        "exit": round(float(exit_price), 4),
        "exit_time": exit_time.isoformat(),
        "outcome": outcome,
        "r": round(float(r), 3),
    }


def resolve_open_trades(ledger: dict, frames_by_interval: dict):
    """frames_by_interval: {interval: {symbol: df}}. Closes whatever resolved."""
    still_open = []
    for trade in ledger["open"]:
        df = frames_by_interval.get(trade["interval"], {}).get(trade["symbol"])
        result = _resolve_one(trade, df) if df is not None else None
        if result is None:
            still_open.append(trade)
            continue
        ledger["closed"].append(close_record(trade, *result))
    ledger["open"] = still_open


def replay_walk(ledger: dict, module, strat_name: str, symbol: str, df, interval: str,
                params: dict, cfg: dict, start_i: int) -> int:
    """
    Walk historical bars through scan_at with correct position sequencing:
    while a virtual position is open, later signals for the same key are
    blocked (as they would be live) until that trade's exit bar has passed.
    """
    import uuid as _uuid
    busy_until = None
    opened = 0
    for i in range(start_i, len(df) - 1):
        ts = df.index[i]
        if busy_until is not None and ts <= busy_until:
            continue
        try:
            sig = module.scan_at(symbol, df, interval, params, cfg, i=i)
        except Exception:  # noqa: BLE001
            continue
        if not sig:
            continue
        key = signal_key(sig)
        if key in ledger["seen"]:
            continue
        ledger["seen"][key] = 1
        trade = {
            "id": _uuid.uuid4().hex[:10],
            "source": "backfill",
            **{k: sig[k] for k in ("strategy", "symbol", "interval", "direction",
                                   "entry", "stop", "target", "risk", "bar_time",
                                   "time_stop_bars", "eod_exit")},
        }
        result = _resolve_one(trade, df)
        opened += 1
        if result is None:
            # unresolved at data end -> carry as an open trade for live cycles
            ledger["open"].append(trade)
            busy_until = df.index[-1]
        else:
            exit_price, exit_time, outcome = result
            ledger["closed"].append(close_record(trade, exit_price, exit_time, outcome))
            busy_until = exit_time
    return opened


def compute_stats(ledger: dict, rolling_window: int) -> list:
    """Per strategy x interval performance table."""
    groups = {}
    for t in ledger["closed"]:
        groups.setdefault((t["strategy"], t["interval"]), []).append(t)

    table = []
    for (strategy, interval), trades in sorted(groups.items()):
        trades.sort(key=lambda t: t["exit_time"])
        rs = [t["r"] for t in trades]
        live = [t for t in trades if t.get("source") == "live"]
        wins = [r for r in rs if r > 0]
        losses = [r for r in rs if r <= 0]
        gross_win, gross_loss = sum(wins), abs(sum(losses))
        recent = rs[-rolling_window:]
        recent_exp = sum(recent) / len(recent) if recent else 0.0

        if len(rs) < 10:
            health = "collecting"
        elif recent_exp > 0.05:
            health = "working"
        elif recent_exp > -0.05:
            health = "flat"
        else:
            health = "degraded"

        table.append({
            "strategy": strategy,
            "interval": interval,
            "trades": len(rs),
            "live_trades": len(live),
            "win_rate": round(100 * len(wins) / len(rs), 1) if rs else 0,
            "avg_r": round(sum(rs) / len(rs), 3) if rs else 0,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else (99.0 if gross_win else 0),
            "recent_avg_r": round(recent_exp, 3),
            "health": health,
        })
    return table
