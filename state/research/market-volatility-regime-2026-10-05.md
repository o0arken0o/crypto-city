# Volatility-Regime Analysis — Ciclo 9

**Data**: 2026-10-05 | **Timeframe**: 1d | **Periodo dati**: 2024-01-09 to 2026-10-04 (1000 candele)

## Mercati Registrati

### XRP-USD (mkt_25e3ce, score 47.2)
- **Volatilità annualizzata**: ~85-95%
- **Caratteristica**: Regimi di bassa/media volatilità osservabili in 2.7 anni, switch regime suggerisce opportunità
- **Autocorrelazione**: Bassa, consona a regime changes
- **Confidence**: 55% (volatilità più prevedibile che pure trend)

### ADA-USD (mkt_ad2753, score 33.6)
- **Volatilità annualizzata**: ~75-80%
- **Caratteristica**: Minore variabilità di regime rispetto a XRP, regimi meno marcati
- **Liquidity (ticket)**: 4/5 buona
- **Confidence**: 48% (regimi sottili, richiede sensibilità di parametri)

### CRO-USD (mkt_e525e9, score 25.0)
- **Volatilità annualizzata**: ~90%+
- **Caratteristica**: Alta volatilità, liquidità inferiore, switch regime osservabile
- **Liquidity (ticket)**: 3/5 moderata
- **Confidence**: 50% (volatilità elevata, meno liquida di ADA/XRP)

## Insights
- **XRP** è il miglior candidato volatility-regime: volatilità robusta, regimi distinguibili, liquidità elevata.
- Strategia volatility-regime richiede **switch fra posizioni lunghe (low-vol regime) e trading ranges (high-vol regime)**.
- **CRO** più rischioso (illiquidità), **ADA** equilibrato ma con regimi sottili.

## Fonti dati
- `scripts/market_data.py XRP-USD/ADA-USD/CRO-USD 1d` (1000 candele pubbliche)
- Metriche: volatilità (std dev log-returns annualizzata), drawdown max, autocorrelazione lag-1
