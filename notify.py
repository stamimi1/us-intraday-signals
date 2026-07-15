"""Telegram pings for fresh signals (HTML parse mode — see market_intel_alerts lesson)."""
import html
import logging
import os

import requests

logger = logging.getLogger(__name__)


def _esc(v) -> str:
    return html.escape(str(v), quote=False)


def send_fresh_signals(signals: list, labels: dict, cfg: dict):
    tg = cfg["notify"]["telegram"]
    if not tg["enabled"] or not signals:
        return
    # push only the intervals the user actually trades (dashboard shows all)
    wanted = tg.get("intervals") or []
    if wanted:
        signals = [s for s in signals if s["interval"] in wanted]
    if not signals:
        return
    token = os.environ.get(tg["bot_token_env"])
    chat_id = os.environ.get(tg["chat_id_env"])
    if not token or not chat_id:
        logger.info("Telegram not configured; skipping %d signal notifications", len(signals))
        return

    for sig in signals[: tg["max_per_cycle"]]:
        arrow = "📈 LONG" if sig["direction"] == "long" else "📉 SHORT"
        text = (
            f"⚡ <b>{_esc(labels.get(sig['strategy'], sig['strategy']))}</b> [{sig['interval']}] — "
            f"<b>{_esc(sig['symbol'])}</b> {arrow}\n"
            f"Entry {sig['entry']} | Stop {sig['stop']} | Target {sig['target']}\n"
            f"<i>{_esc(sig['reason'])}</i>"
        )
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
                timeout=10,
            )
            if r.status_code >= 400:
                logger.error("Telegram %s: %s", r.status_code, r.text[:200])
        except requests.RequestException as exc:
            logger.error("Telegram send failed: %s", exc)
