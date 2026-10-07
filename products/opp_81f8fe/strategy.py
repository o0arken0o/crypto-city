PAIR = "SOL-USD"
TIMEFRAME = "1d"
PARAMS = {"roc": 60, "sma": 50}


def target(c, p):
    cl = c["close"]
    n = max(p["roc"] + 1, p["sma"])
    if len(cl) < n:
        return 0.0
    roc = cl[-1] / cl[-1 - p["roc"]] - 1.0
    sma = sum(cl[-p["sma"]:]) / p["sma"]
    return 1.0 if roc > 0 and cl[-1] > sma else 0.0
