PAIR = "ETH-USD"
TIMEFRAME = "1d"
# Bollinger band strategy: long when price below lower band, exit when above upper band
PARAMS = {"sma": 20, "k_std": 2}

import math

def target(c, p):
    cl = c["close"]
    if len(cl) < p["sma"]:
        return 0.0
    sma = sum(cl[-p["sma"]:]) / p["sma"]
    mean = sma
    var = sum((x - mean) ** 2 for x in cl[-p["sma"]:]) / (p["sma"] - 1)
    std = math.sqrt(var)
    lower = sma - p["k_std"] * std
    upper = sma + p["k_std"] * std
    if cl[-1] < lower:
        return 1.0
    if cl[-1] > upper:
        return 0.0
    return 0.0