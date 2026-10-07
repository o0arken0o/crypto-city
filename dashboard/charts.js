// Real candlestick charts on a 2D canvas, shared by the panel (index.html) and the 3D rooms (exchange.js).
// Data: /api/candles (Coinbase Exchange, see server.py crypto_candles). Never invents prices: no data → says so.
// real candles: d.candles = [[time, open, high, low, close, volume], ...] oldest first (the last one is still forming)
export const fmtPrice = (v, cur) => v.toLocaleString("it-IT", { style: "currency", currency: cur, maximumFractionDigits: v >= 1000 ? 0 : 2 });
export function drawRealCandles(g, w, h, d, title, accent = "#3aa0ff", opts = {}) {
  const k = opts.scale || h / 400, cur = (d && d.pair || "-EUR").split("-")[1], cs = (d && d.candles) || [];
  g.fillStyle = "#030918"; g.fillRect(0, 0, w, h);
  g.font = `600 ${Math.round(24 * k)}px Chakra Petch, sans-serif`; g.textBaseline = "alphabetic"; g.textAlign = "left";
  if (!opts.bare) { g.fillStyle = "#cfe3ff"; g.fillText(title, 18 * k, 32 * k); }
  if (!cs.length) { g.fillStyle = "#8ea3c8"; g.textAlign = "center"; g.fillText(d && d.loading ? "carico i dati…" : "dati non disponibili", w / 2, h / 2); return; }
  const vh = opts.volume ? h * .18 : 0;  // volume bars under the candles
  const top = (opts.bare ? 40 : 56) * k, bot = h - 16 * k - vh, right = w - 92 * k, left = 12 * k;
  if (vh) {
    const vmax = Math.max(...cs.map(c => c[5]), 1e-9), st = (right - left) / cs.length;
    cs.forEach((c, i) => { g.fillStyle = c[4] >= c[1] ? "rgba(47,213,155,.45)" : "rgba(255,77,106,.45)"; const hh = c[5] / vmax * (vh - 8 * k); g.fillRect(left + i * st + st * .19, h - 6 * k - hh, Math.max(1, st * .62), hh); });
    g.fillStyle = "#6f86b0"; g.font = `500 ${Math.round(13 * k)}px Chakra Petch, sans-serif`; g.textAlign = "left"; g.fillText("volume", right + 8 * k, h - vh + 10 * k);
  }
  let lo = Infinity, hi = -Infinity; for (const c of cs) { lo = Math.min(lo, c[3]); hi = Math.max(hi, c[2]); }
  const pad = (hi - lo) * .06 || 1; lo -= pad; hi += pad;
  const Y = v => top + (hi - v) / (hi - lo) * (bot - top), step = (right - left) / cs.length;
  g.strokeStyle = "rgba(80,150,255,.14)"; g.lineWidth = 1; g.fillStyle = "#6f86b0"; g.font = `500 ${Math.round(15 * k)}px Chakra Petch, sans-serif`;
  for (let i = 0; i <= 4; i++) { const v = lo + (hi - lo) * i / 4, y = Y(v); g.beginPath(); g.moveTo(left, y); g.lineTo(right, y); g.stroke(); g.fillText(fmtPrice(v, cur), right + 8 * k, y + 5 * k); }
  cs.forEach((c, i) => {
    const x = left + i * step + step / 2, up = c[4] >= c[1];
    g.strokeStyle = g.fillStyle = up ? "#2fd59b" : "#ff4d6a"; g.lineWidth = Math.max(1, 1.6 * k);
    g.beginPath(); g.moveTo(Math.round(x) + .5, Y(c[2])); g.lineTo(Math.round(x) + .5, Y(c[3])); g.stroke();
    const bw = Math.max(2, step * .62), y0 = Y(Math.max(c[1], c[4])), y1 = Y(Math.min(c[1], c[4]));
    g.fillRect(Math.round(x - bw / 2), Math.round(y0), Math.round(bw), Math.max(1, Math.round(y1 - y0)));
  });
  g.strokeStyle = accent; g.lineWidth = 2.5 * k; g.beginPath();  // 10-candle average
  cs.forEach((c, i) => { const a = cs.slice(Math.max(0, i - 9), i + 1), m = a.reduce((t, q) => t + q[4], 0) / a.length, x = left + i * step + step / 2; i ? g.lineTo(x, Y(m)) : g.moveTo(x, Y(m)); });
  g.stroke();
  const last = cs[cs.length - 1][4], ch = (last / cs[0][1] - 1) * 100;
  if (!opts.bare) {
    g.textAlign = "right"; g.font = `700 ${Math.round(24 * k)}px Chakra Petch, sans-serif`; g.fillStyle = "#e6efff"; g.fillText(fmtPrice(last, cur), w - 150 * k, 32 * k);
    g.fillStyle = ch >= 0 ? "#2fd59b" : "#ff4d6a"; g.fillText((ch >= 0 ? "+" : "") + ch.toFixed(2).replace(".", ",") + "%", w - 18 * k, 32 * k);
  }
  g.textAlign = "left"; g.font = `600 ${Math.round(13 * k)}px Chakra Petch, sans-serif`; g.fillStyle = "#2fd59b";
  g.fillText("● LIVE · Coinbase · " + new Date().toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }) + (opts.bare ? ` · ${cs.length} candele` : ""), 18 * k, (opts.bare ? 26 : 50) * k);
}


// small line of closing prices (for the market cards)
export function sparkline(g, w, h, cs, up) {
  g.clearRect(0, 0, w, h);
  if (!cs || cs.length < 2) return;
  const v = cs.map(c => c[4]), lo = Math.min(...v), hi = Math.max(...v), Y = x => h - 3 - (x - lo) / ((hi - lo) || 1) * (h - 6);
  const col = up ? "#2fd59b" : "#ff4d6a", gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, up ? "rgba(47,213,155,.35)" : "rgba(255,77,106,.35)"); gr.addColorStop(1, "rgba(0,0,0,0)");
  g.beginPath(); v.forEach((x, i) => { const px = i / (v.length - 1) * w; i ? g.lineTo(px, Y(x)) : g.moveTo(px, Y(x)); });
  g.strokeStyle = col; g.lineWidth = 2; g.stroke(); g.lineTo(w, h); g.lineTo(0, h); g.closePath(); g.fillStyle = gr; g.fill();
}
