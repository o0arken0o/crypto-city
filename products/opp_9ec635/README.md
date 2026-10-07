# opp_9ec635 - Mean-reversion BTC-USD 1h

Regole (solo spot, niente leva né short):
- Calcola lo z-score del prezzo di chiusura su 48 candele orarie.
- Compra (100%) quando lo z-score scende a -2 o meno; torna in cassa quando risale a 0.
- Commissioni 0,10% + slittamento 0,05% a ogni cambio.

Backtest (2026-07-13 -> 2026-10-04, solo ~3 mesi di dati orari):
- Strategia: +2,9%, drawdown 3%, Sharpe 0,92; out-of-sample +0,7%, Sharpe 0,65.
- Buy & hold: +39,1%, drawdown 8%. 38 operazioni. Esito: PASS.

Rischi: periodo breve, guadagno OOS minimo, resta fuori nei trend rialzisti; in un crollo prolungato compra "il ribasso" e può perdere.
Backtest: risultati simulati, non garantiscono quelli futuri.
