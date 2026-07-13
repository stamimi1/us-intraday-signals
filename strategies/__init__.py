"""Strategy registry: name -> module implementing scan()/scan_at()."""
from strategies import ema_cross, orb, rsi2, squeeze, vwap_reversion

REGISTRY = {
    orb.NAME: orb,
    vwap_reversion.NAME: vwap_reversion,
    ema_cross.NAME: ema_cross,
    rsi2.NAME: rsi2,
    squeeze.NAME: squeeze,
}

LABELS = {
    "orb": "Opening Range Breakout",
    "vwap_reversion": "VWAP Reversion",
    "ema_cross": "EMA 9/21 Trend Cross",
    "rsi2": "RSI-2 Pullback",
    "squeeze": "Squeeze Breakout",
}
