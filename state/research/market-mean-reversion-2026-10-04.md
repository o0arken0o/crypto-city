# Market: BTC 1h Mean-Reversion

**Ciclo 4 · 2026-10-04**

## Idea
BTC 1-hour timeframe con segnali di mean-reversion: autocorrelazione lag=1 negativa (-0.067), indicativa di overshoots seguiti da correzioni rapide. Diversa dalle 10 killed trend-following ideas.

## Metriche (candele 1h, ultimi 30 giorni)
- **Autocorrelazione(lag=1):** -0.067 ← signature di mean-reversion
- **Volatilità annualizzata:** 5.0%
- **Drawdown:** -3.0%
- **Rendimento 30d:** +2.1%
- **Giorni di candele:** 720 (2025-09-04 → 2026-10-03)

## Parametri registrati
- name: "BTC 1h mean-reversion"
- strategy: mean-reversion
- demand: 3 (fenomeno moderato)
- ticket: 5 (BTC è maximally liquid)
- speed: 4 (1h = opportunità frequenti)
- competition: 3 (mean-reversion non saturo come trend)
- confidence: 0.55 (statistica solida ma sample limitato)
- Market ID: mkt_58df21, score 48.8

## Prossimi passi
Quant-analyst valida il concetto; quant-dev codifica mean-reversion su BTC 1h con regola di entrata/uscita basata su autocorrelazione e RSI.
