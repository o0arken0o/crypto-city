import math
PAIR = "BTC-USD"; TIMEFRAME = "1h"
PARAMS = {"win": 48, "entry": -2.0, "exit": 0.0, "replay": 72}

def _z(cl, end, w):
    s = cl[end - w:end]
    m = sum(s) / w
    sd = math.sqrt(sum((x - m) ** 2 for x in s) / w)
    return 0.0 if sd == 0 else (cl[end - 1] - m) / sd

def target(c, p):
    cl = c["close"]; w = p["win"]
    if len(cl) < w + 1: return 0.0
    n = len(cl); start = max(w, n - p["replay"])
    pos = 0.0
    for e in range(start, n + 1):
        z = _z(cl, e, w)
        if pos == 0.0 and z <= p["entry"]: pos = 1.0
        elif pos == 1.0 and z >= p["exit"]: pos = 0.0
    return pos
