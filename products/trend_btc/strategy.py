PAIR = "BTC-USD"
TIMEFRAME = "1d"
PARAMS = {"fast": 50, "slow": 200}

def target(c, p):
    cl = c["close"]
    if len(cl) < p["slow"]:
        return 0.0
    fast_ma = sum(cl[-p["fast"]:]) / p["fast"]
    slow_ma = sum(cl[-p["slow"]:]) / p["slow"]
    # Trend filter: price must be above slow MA
    if cl[-1] < slow_ma:
        return 0.0
    # Simple trailing stop: exit if price falls >10% from max in lookback
    max_recent = max(cl[-p["slow"]:])
    if cl[-1] < 0.9 * max_recent:
        return 0.0
    return 1.0 if fast_ma > slow_ma else 0.0
